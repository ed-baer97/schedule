"""Excel import service — writes only via catalog/assignment services."""
from __future__ import annotations

from collections import defaultdict
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

    def import_subject_hours(self, file_path, subject_name: str | None = None) -> dict:
        """
        Import one subject file: teachers × classes, cells = hours per week.

        Column A — teacher names. Remaining columns — classes.
        Subject name: explicit argument, otherwise the file stem.
        """
        import pandas as pd

        df = pd.read_excel(file_path)
        if df.empty or len(df.columns) < 2:
            raise ValueError(
                "В файле нужны столбец учителей и хотя бы один столбец класса"
            )

        df.columns = df.columns.astype(str).str.strip()
        teacher_col = df.columns[0]
        class_cols = [c for c in df.columns[1:] if c and c.lower() != "nan"]
        if not class_cols:
            raise ValueError("Нет столбцов с классами")

        resolved_subject = (subject_name or Path(file_path).stem).strip()
        if not resolved_subject:
            raise ValueError("Не удалось определить название предмета")

        subject, subject_created = self._subjects.ensure(
            resolved_subject, commit=False
        )

        created_teachers = 0
        created_classes = 0
        created_assignments = 0
        updated_assignments = 0
        warnings: list[str] = []
        by_class: dict[int, list[tuple[Teacher, int]]] = defaultdict(list)

        for _, row in df.iterrows():
            raw_name = row.get(teacher_col)
            if raw_name is None or (isinstance(raw_name, float) and pd.isna(raw_name)):
                continue
            teacher_name = " ".join(str(raw_name).split())
            if not teacher_name or teacher_name.lower() == "nan":
                continue

            teacher, t_new = self._get_or_create_teacher(teacher_name)
            if t_new:
                created_teachers += 1

            for col in class_cols:
                hours = _parse_hours(row.get(col))
                if hours <= 0:
                    continue
                class_name = str(col).strip()
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
                self._assignments.set_group_numbers(
                    [ordered[0].id], [None], commit=False
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
