"""Excel import service — writes only via catalog/assignment services."""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.domain import grade_from_name, level_from_grade, normalize_person_name
from app.models import SchoolClass, Subject, Teacher, TeachingAssignment
from app.services.assignment_service import AssignmentService
from app.services.classroom_service import ClassroomService
from app.services.school_class_service import SchoolClassService
from app.services.subject_service import SubjectService
from app.services.teacher_service import TeacherService

_MAX_GROUPS = 4
_CLASS_NAME_RE = re.compile(r"^(\d{1,2})\s*([^\W\d_]{1,3})$", re.UNICODE)
_YEAR_RE = re.compile(r"^\d{4}\s*[-–/]\s*\d{2,4}$")
_TEACHER_HEADER_KEYS = frozenset(
    {"фио", "учитель", "учителя", "teacher", "teachers"}
)
_IGNORE_HEADER_KEYS = frozenset(
    {
        "n",
        "nn",
        "no",
        "пп",
        "итого",
        "всего",
        "сумма",
        "час",
        "часов",
        "нагрузка",
    }
)
_GENERIC_SHEET_KEYS = frozenset(
    {"sheet", "sheet1", "sheet2", "лист", "лист1", "лист2"}
)


def _cell_text(value) -> str:
    import pandas as pd

    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, bool):
        return ""
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return str(value).strip()
    return " ".join(str(value).split())


def _header_key(text: str) -> str:
    folded = text.casefold().strip()
    if folded in {"№", "#"}:
        return "n"
    return "".join(ch for ch in folded if ch.isalnum())


def _is_class_name(text: str) -> bool:
    return bool(text and _CLASS_NAME_RE.match(text.replace(" ", "")))


def _is_teacher_header(text: str) -> bool:
    return _header_key(text) in _TEACHER_HEADER_KEYS


def _is_ignore_header(text: str) -> bool:
    key = _header_key(text)
    return key in _IGNORE_HEADER_KEYS or key.startswith("итого")


def _is_generic_sheet(name: str) -> bool:
    return _header_key(name) in _GENERIC_SHEET_KEYS


@dataclass(frozen=True)
class _HoursSheet:
    teacher_col: int
    class_columns: tuple[tuple[int, str], ...]
    header_row: int
    sheet_name: str
    subject_hint: str | None
    frame: object


def _subject_from_title_rows(rows: list[list[str]]) -> str | None:
    for values in rows:
        for text in values:
            if not text or len(text) < 2:
                continue
            if _YEAR_RE.match(text) or _is_class_name(text):
                continue
            if _is_teacher_header(text) or _is_ignore_header(text):
                continue
            if _is_generic_sheet(text):
                continue
            return text
    return None


def _pick_header_row(df) -> int:
    best_idx = -1
    best_score = 0
    scan = min(len(df), 20)
    for idx in range(scan):
        values = [_cell_text(v) for v in df.iloc[idx].tolist()]
        score = sum(1 for text in values if _is_class_name(text))
        if score > best_score:
            best_score = score
            best_idx = idx
    if best_idx < 0 or best_score < 1:
        raise ValueError("Не найдена строка с классами (1А, 5Б, 11Г…)")
    return best_idx


def _read_hours_sheet(file_path) -> _HoursSheet:
    import pandas as pd

    with pd.ExcelFile(file_path) as xl:
        sheet_name = str(xl.sheet_names[0]).strip() if xl.sheet_names else ""
        df = pd.read_excel(xl, sheet_name=0, header=None)

    if df.empty or df.shape[1] < 2:
        raise ValueError(
            "В файле нужны столбец учителей и хотя бы один столбец класса"
        )

    header_row = _pick_header_row(df)
    headers = [_cell_text(v) for v in df.iloc[header_row].tolist()]

    teacher_col: int | None = None
    for idx, text in enumerate(headers):
        if _is_teacher_header(text):
            teacher_col = idx
            break
    if teacher_col is None:
        for idx, text in enumerate(headers):
            if text and not _is_class_name(text) and not _is_ignore_header(text):
                teacher_col = idx
                break
    if teacher_col is None:
        raise ValueError("Не найден столбец с ФИО учителей")

    class_columns: list[tuple[int, str]] = []
    seen_classes: set[str] = set()
    for idx, text in enumerate(headers):
        if idx == teacher_col or not _is_class_name(text):
            continue
        class_name = text.replace(" ", "")
        if class_name in seen_classes:
            continue
        seen_classes.add(class_name)
        class_columns.append((idx, class_name))
    if not class_columns:
        raise ValueError("Нет столбцов с классами")

    title_rows = [
        [_cell_text(v) for v in df.iloc[r].tolist()]
        for r in range(header_row)
    ]
    subject_hint = _subject_from_title_rows(title_rows)
    if not subject_hint and sheet_name and not _is_generic_sheet(sheet_name):
        subject_hint = sheet_name

    return _HoursSheet(
        teacher_col=teacher_col,
        class_columns=tuple(class_columns),
        header_row=header_row,
        sheet_name=sheet_name,
        subject_hint=subject_hint,
        frame=df,
    )


def _resolve_subject_name(
    *,
    explicit: str | None,
    sheet: _HoursSheet,
    file_path,
    filename: str | None,
) -> str:
    for candidate in (
        (explicit or "").strip(),
        (sheet.subject_hint or "").strip(),
        Path(filename).stem.strip() if filename else "",
        Path(file_path).stem.strip(),
    ):
        if candidate and not _is_generic_sheet(candidate):
            return candidate
    raise ValueError("Не удалось определить название предмета")


def _is_teacher_name(text: str) -> bool:
    if not text or text.casefold() == "nan":
        return False
    if _is_teacher_header(text) or _is_ignore_header(text) or _is_class_name(text):
        return False
    if text.isdigit():
        return False
    return True


def _parse_hours(value) -> int:
    import pandas as pd

    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 0
    if isinstance(value, str):
        text = value.strip().replace(",", ".")
        if not text or text.lower() == "nan":
            return 0
        value = text
    try:
        hours = int(float(value))
    except (ValueError, TypeError):
        return 0
    return max(0, hours)


def _grade_and_level(class_name: str) -> tuple[int, str]:
    grade = grade_from_name(class_name)
    return grade, level_from_grade(grade)


class ExcelImporter:
    """Service for importing data from Excel files."""

    def __init__(self, session: Session, school_id: int):
        self.session = session
        self.school_id = school_id
        self._teachers = TeacherService(session, school_id)
        self._classrooms = ClassroomService(session, school_id)
        self._subjects = SubjectService(session, school_id)
        self._classes = SchoolClassService(session, school_id)
        self._assignments = AssignmentService(session, school_id)
        self._teachers_by_name: dict[str, Teacher] = {}
        self._classes_by_name: dict[str, SchoolClass] = {}

    def import_teachers(self, file_path):
        """
        Import teachers from Excel file.
        Expected columns: ФИО, Email, Телефон
        Returns count of imported teachers.
        """
        import pandas as pd

        df = pd.read_excel(file_path)
        df.columns = df.columns.str.strip()

        count = 0
        for _, row in df.iterrows():
            full_name = str(row.get("ФИО", "")).strip()
            if not full_name or full_name == "nan":
                continue

            email = (
                str(row.get("Email", "")).strip()
                if pd.notna(row.get("Email"))
                else None
            )
            phone = (
                str(row.get("Телефон", "")).strip()
                if pd.notna(row.get("Телефон"))
                else None
            )
            _, created = self._teachers.ensure(
                full_name, email=email or None, phone=phone or None, commit=False
            )
            if created:
                count += 1

        self.session.commit()
        return count

    def import_classrooms(self, file_path):
        """
        Import classrooms from Excel file.
        Expected columns: Номер, Название, Вместимость классов, Этаж, Корпус
        Returns count of imported classrooms.
        """
        import pandas as pd

        df = pd.read_excel(file_path)
        df.columns = df.columns.str.strip()

        count = 0
        for _, row in df.iterrows():
            number = str(row.get("Номер", "")).strip()
            if not number or number == "nan":
                continue

            floor = row.get("Этаж")
            classes_cap = row.get("Вместимость классов", row.get("Вместимость", 1))
            try:
                classes_cap = int(float(classes_cap)) if pd.notna(classes_cap) else 1
            except (ValueError, TypeError):
                classes_cap = 1
            classes_cap = max(1, classes_cap)

            _, created = self._classrooms.ensure(
                number=number,
                name=(
                    str(row.get("Название", "")).strip()
                    if pd.notna(row.get("Название"))
                    else None
                ),
                floor=int(floor) if pd.notna(floor) else None,
                building=(
                    str(row.get("Корпус", "")).strip()
                    if pd.notna(row.get("Корпус"))
                    else None
                ),
                classes_capacity=classes_cap,
                commit=False,
            )
            if created:
                count += 1

        self.session.commit()
        return count

    def import_curriculum(self, file_path, school_level):
        """
        Import curriculum (subjects x classes) from Excel.
        Rows = classes (first column)
        Columns = subjects (header row)
        Cells = hours per week (0 = not taught)

        Returns tuple (subjects_count, assignments_count)
        """
        import pandas as pd

        df = pd.read_excel(file_path, index_col=0)
        df.index = df.index.astype(str).str.strip()
        df.columns = df.columns.str.strip()

        created_subjects = 0
        created_assignments = 0

        subjects_map: dict[str, Subject] = {}
        for subject_name in df.columns:
            subject_name = str(subject_name).strip()
            if not subject_name or subject_name == "nan":
                continue
            subject, created = self._subjects.ensure(
                subject_name, color=Subject.DEFAULT_COLOR, commit=False
            )
            if created:
                created_subjects += 1
            subjects_map[subject_name] = subject

        for class_name in df.index:
            class_name = str(class_name).strip()
            if not class_name or class_name == "nan":
                continue

            school_class, _ = self._classes.ensure(
                class_name, school_level=school_level, commit=False
            )

            for subject_name in df.columns:
                subject_name = str(subject_name).strip()
                if subject_name not in subjects_map:
                    continue

                try:
                    hours = int(df.loc[class_name, subject_name])
                except (ValueError, TypeError):
                    hours = 0

                if hours == 0:
                    continue

                subject = subjects_map[subject_name]
                _, created = self._assignments.upsert_hours(
                    subject_id=subject.id,
                    class_id=school_class.id,
                    hours_per_week=hours,
                    teacher_id=None,
                    match_null_teacher=True,
                    commit=False,
                )
                if created:
                    created_assignments += 1

        self.session.commit()
        return created_subjects, created_assignments

    def import_subject_hours(
        self,
        file_path,
        subject_name: str | None = None,
        *,
        filename: str | None = None,
    ) -> dict:
        """
        Import one subject file: teachers × classes, cells = hours per week.

        Accepts the school workbook: title row with the subject name, then a
        header (№ / ФИО / classes / итого). The older one-row header
        (Учитель, 1А, …) still works.

        Subject name: explicit argument, else title/sheet, else file stem.
        Same normalized ФИО across files reuses the Teacher row.
        """
        sheet = _read_hours_sheet(file_path)
        resolved_subject = _resolve_subject_name(
            explicit=subject_name,
            sheet=sheet,
            file_path=file_path,
            filename=filename,
        )

        subject, subject_created = self._subjects.ensure(
            resolved_subject, commit=False
        )

        created_teachers = 0
        created_classes = 0
        created_assignments = 0
        updated_assignments = 0
        warnings: list[str] = []
        by_class: dict[int, list[tuple[Teacher, int]]] = defaultdict(list)
        df = sheet.frame

        for row_idx in range(sheet.header_row + 1, len(df)):
            row = df.iloc[row_idx]
            teacher_name = _cell_text(row.iloc[sheet.teacher_col])
            if not _is_teacher_name(teacher_name):
                continue

            teacher, t_new = self._get_or_create_teacher(teacher_name)
            if t_new:
                created_teachers += 1

            for col_idx, class_name in sheet.class_columns:
                hours = _parse_hours(row.iloc[col_idx])
                if hours <= 0:
                    continue
                school_class, c_new = self._get_or_create_class_inferred(class_name)
                if c_new:
                    created_classes += 1
                by_class[school_class.id].append((teacher, hours))

        subgroup_classes = 0
        for class_id, rows in by_class.items():
            seen: dict[int, TeachingAssignment] = {}
            ordered: list[TeachingAssignment] = []
            for teacher, hours in rows:
                existing = seen.get(teacher.id)
                if existing is not None:
                    existing.hours_per_week += hours
                    warnings.append(
                        f"{resolved_subject}: учитель «{teacher.full_name}» "
                        f"повторяется в одном классе — часы сложены"
                    )
                    continue
                assignment, created = self._assignments.upsert_hours(
                    subject_id=subject.id,
                    class_id=class_id,
                    hours_per_week=hours,
                    teacher_id=teacher.id,
                    commit=False,
                )
                seen[teacher.id] = assignment
                ordered.append(assignment)
                if created:
                    created_assignments += 1
                else:
                    updated_assignments += 1

            n = len(ordered)
            if n >= 2:
                subgroup_classes += 1
                if n > _MAX_GROUPS:
                    warnings.append(
                        f"{resolved_subject}: в классе больше {_MAX_GROUPS} учителей "
                        f"— сохранены все, группы пронумерованы по порядку"
                    )
                self._assignments.set_group_numbers(
                    [a.id for a in ordered],
                    list(range(1, n + 1)),
                    commit=False,
                )
            elif n == 1:
                group = None
                self._assignments.set_group_numbers(
                    [ordered[0].id], [group], commit=False
                )

        self.session.commit()
        return {
            "subject": subject.name,
            "subject_created": subject_created,
            "teachers_created": created_teachers,
            "classes_created": created_classes,
            "assignments_created": created_assignments,
            "assignments_updated": updated_assignments,
            "subgroup_classes": subgroup_classes,
            "warnings": warnings,
        }

    def _get_or_create_teacher(self, full_name: str) -> tuple[Teacher, bool]:
        key = normalize_person_name(full_name)
        cached = self._teachers_by_name.get(key)
        if cached is not None:
            return cached, False
        teacher, created = self._teachers.ensure(full_name, commit=False)
        self._teachers_by_name[key] = teacher
        return teacher, created

    def _get_or_create_class_inferred(self, name: str) -> tuple[SchoolClass, bool]:
        cached = self._classes_by_name.get(name)
        if cached is not None:
            return cached, False
        _grade, level = _grade_and_level(name)
        school_class, created = self._classes.ensure(
            name, school_level=level, commit=False
        )
        self._classes_by_name[name] = school_class
        return school_class, created
