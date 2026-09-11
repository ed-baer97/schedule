"""Teacher catalog CRUD."""
from __future__ import annotations

import io
from collections import defaultdict

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.domain.names import normalize_person_name
from app.models import Classroom, SchoolClass, Teacher, TeachingAssignment
from app.services.dto import (
    TeacherData,
    TeacherLoadData,
    TeacherShiftBriefData,
    TeacherSubjectHoursData,
    teacher_data,
)
from app.services.errors import NotFoundError
from app.services.report_service import ExportFile
from app.services.tenancy import require_owned

_HEADER_FILL = PatternFill("solid", fgColor="147F78")
_HEADER_FONT = Font(bold=True, size=11, color="F4FFFD", name="Calibri")
_CELL_FONT = Font(size=11, color="14201A", name="Calibri")
_TOTAL_FONT = Font(bold=True, size=11, color="14201A", name="Calibri")
_GRID = Border(
    left=Side(style="thin", color="2C3A34"),
    right=Side(style="thin", color="2C3A34"),
    top=Side(style="thin", color="2C3A34"),
    bottom=Side(style="thin", color="2C3A34"),
)
_HEADER_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=True)
_CELL_ALIGN = Alignment(horizontal="left", vertical="center", wrap_text=True)
_NUM_ALIGN = Alignment(horizontal="center", vertical="center")


def _join_hours(parts: list[tuple[str, int]]) -> str:
    return "; ".join(f"{name}: {hours}" for name, hours in parts)


class TeacherService:
    def __init__(self, db: Session, school_id: int):
        self.db = db
        self.school_id = school_id

    def _load_one(self, teacher_id: int) -> Teacher:
        stmt = (
            select(Teacher)
            .options(joinedload(Teacher.home_classroom))
            .where(Teacher.id == teacher_id, Teacher.school_id == self.school_id)
        )
        teacher = self.db.execute(stmt).scalars().unique().one_or_none()
        if teacher is None:
            raise NotFoundError("Teacher not found")
        return teacher

    def list(self) -> list[TeacherData]:
        stmt = (
            select(Teacher)
            .options(joinedload(Teacher.home_classroom))
            .where(Teacher.school_id == self.school_id)
            .order_by(Teacher.full_name)
        )
        return [
            teacher_data(t)
            for t in self.db.execute(stmt).scalars().unique().all()
        ]

    def get(self, teacher_id: int) -> TeacherData:
        return teacher_data(self._load_one(teacher_id))

    def list_load(self) -> list[TeacherLoadData]:
        """ФИО, часы в неделю по предметам и смены классов, которые ведёт учитель."""
        teachers = list(
            self.db.execute(
                select(Teacher)
                .where(Teacher.school_id == self.school_id)
                .order_by(Teacher.full_name)
            )
            .scalars()
            .all()
        )
        assignments = list(
            self.db.execute(
                select(TeachingAssignment)
                .options(
                    joinedload(TeachingAssignment.subject),
                    joinedload(TeachingAssignment.school_class).joinedload(
                        SchoolClass.shift
                    ),
                )
                .where(
                    TeachingAssignment.school_id == self.school_id,
                    TeachingAssignment.teacher_id.isnot(None),
                )
            )
            .scalars()
            .unique()
            .all()
        )
        by_teacher: dict[int, list[TeachingAssignment]] = defaultdict(list)
        for assignment in assignments:
            if assignment.teacher_id is None:
                continue
            if int(assignment.hours_per_week or 0) <= 0:
                continue
            by_teacher[int(assignment.teacher_id)].append(assignment)
        return [self._load_row(teacher, by_teacher.get(int(teacher.id), [])) for teacher in teachers]

    def export_load(self) -> ExportFile:
        """Excel: сводка нагрузки учителей и детализация по предметам."""
        rows = self.list_load()
        workbook = Workbook()

        summary = workbook.active
        summary.title = "Нагрузка"
        summary_headers = ("ФИО", "Предметы, часы в неделю", "Часы по сменам", "Всего")
        for col, title in enumerate(summary_headers, start=1):
            cell = summary.cell(1, col, title)
            cell.fill = _HEADER_FILL
            cell.font = _HEADER_FONT
            cell.alignment = _HEADER_ALIGN
            cell.border = _GRID

        for row_idx, row in enumerate(rows, start=2):
            subjects = _join_hours([(s.subject_name, s.hours) for s in row.subjects])
            shifts = [(s.name, s.hours) for s in row.shifts]
            if row.unassigned_shift_hours > 0:
                shifts.append(("без смены", row.unassigned_shift_hours))
            values = (
                row.full_name,
                subjects or "нет назначений",
                _join_hours(shifts) if shifts else "—",
                row.total_hours,
            )
            for col, value in enumerate(values, start=1):
                cell = summary.cell(row_idx, col, value)
                cell.font = _TOTAL_FONT if col == 4 else _CELL_FONT
                cell.alignment = _NUM_ALIGN if col == 4 else _CELL_ALIGN
                cell.border = _GRID

        summary.column_dimensions["A"].width = 32
        summary.column_dimensions["B"].width = 48
        summary.column_dimensions["C"].width = 36
        summary.column_dimensions["D"].width = 10
        summary.freeze_panes = "A2"
        summary.auto_filter.ref = f"A1:D{max(1, len(rows) + 1)}"

        detail = workbook.create_sheet("По предметам")
        detail_headers = ("ФИО", "Предмет", "Часы")
        for col, title in enumerate(detail_headers, start=1):
            cell = detail.cell(1, col, title)
            cell.fill = _HEADER_FILL
            cell.font = _HEADER_FONT
            cell.alignment = _HEADER_ALIGN
            cell.border = _GRID

        detail_row = 2
        for row in rows:
            if not row.subjects:
                for col, value in enumerate((row.full_name, "нет назначений", 0), start=1):
                    cell = detail.cell(detail_row, col, value)
                    cell.font = _CELL_FONT
                    cell.alignment = _NUM_ALIGN if col == 3 else _CELL_ALIGN
                    cell.border = _GRID
                detail_row += 1
                continue
            for subject in row.subjects:
                values = (row.full_name, subject.subject_name, subject.hours)
                for col, value in enumerate(values, start=1):
                    cell = detail.cell(detail_row, col, value)
                    cell.font = _CELL_FONT
                    cell.alignment = _NUM_ALIGN if col == 3 else _CELL_ALIGN
                    cell.border = _GRID
                detail_row += 1

        for col in range(1, 4):
            detail.column_dimensions[get_column_letter(col)].width = (32, 28, 10)[col - 1]
        detail.freeze_panes = "A2"
        detail.auto_filter.ref = f"A1:C{max(1, detail_row - 1)}"

        buf = io.BytesIO()
        workbook.save(buf)
        return ExportFile(buf, "нагрузка_учителей.xlsx")

    @staticmethod
    def _load_row(teacher: Teacher, rows: list[TeachingAssignment]) -> TeacherLoadData:
        subject_hours: dict[int, TeacherSubjectHoursData] = {}
        shifts: dict[int, TeacherShiftBriefData] = {}
        unassigned_hours = 0
        for assignment in rows:
            hours = int(assignment.hours_per_week or 0)
            subject = assignment.subject
            current = subject_hours.get(int(subject.id))
            if current is None:
                subject_hours[int(subject.id)] = TeacherSubjectHoursData(
                    subject_id=int(subject.id),
                    subject_name=subject.name,
                    color=subject.display_color,
                    hours=hours,
                )
            else:
                current.hours += hours
            school_class = assignment.school_class
            shift = getattr(school_class, "shift", None)
            if shift is None:
                unassigned_hours += hours
                continue
            shift_row = shifts.get(int(shift.id))
            if shift_row is None:
                shifts[int(shift.id)] = TeacherShiftBriefData(
                    id=int(shift.id),
                    name=shift.name,
                    school_level=shift.school_level,
                    hours=hours,
                )
            else:
                shift_row.hours += hours
        subjects = sorted(subject_hours.values(), key=lambda s: s.subject_name.lower())
        level_order = {"elementary": 0, "secondary": 1}
        shift_list = sorted(
            shifts.values(),
            key=lambda s: (level_order.get(s.school_level, 9), s.name.lower()),
        )
        return TeacherLoadData(
            id=int(teacher.id),
            full_name=teacher.full_name,
            subjects=subjects,
            shifts=shift_list,
            total_hours=sum(s.hours for s in subjects),
            unassigned_shift_hours=unassigned_hours,
            has_classes_without_shift=unassigned_hours > 0,
        )

    def create(
        self,
        *,
        full_name: str,
        email: str | None = None,
        phone: str | None = None,
        home_classroom_id: int | None = None,
        commit: bool = True,
    ) -> TeacherData | Teacher:
        if home_classroom_id is not None:
            require_owned(self.db, Classroom, home_classroom_id, self.school_id)
        t = Teacher(
            school_id=self.school_id,
            full_name=full_name.strip(),
            email=(email or "").strip() or None,
            phone=(phone or "").strip() or None,
            home_classroom_id=home_classroom_id,
        )
        self.db.add(t)
        if commit:
            self.db.commit()
            self.db.refresh(t)
            return teacher_data(self._load_one(t.id))
        self.db.flush()
        return t

    def find_by_full_name(self, full_name: str) -> Teacher | None:
        key = normalize_person_name(full_name)
        stmt = select(Teacher).where(Teacher.school_id == self.school_id)
        for t in self.db.scalars(stmt).all():
            if normalize_person_name(t.full_name) == key:
                return t
        return None

    def ensure(
        self,
        full_name: str,
        *,
        email: str | None = None,
        phone: str | None = None,
        commit: bool = False,
    ) -> tuple[Teacher, bool]:
        existing = self.find_by_full_name(full_name)
        if existing is not None:
            return existing, False
        created = self.create(
            full_name=full_name, email=email, phone=phone, commit=False
        )
        assert isinstance(created, Teacher)
        if commit:
            self.db.commit()
        return created, True

    def update(
        self,
        teacher_id: int,
        *,
        full_name: str | None = None,
        email: str | None = None,
        phone: str | None = None,
        home_classroom_id: int | None = None,
        fields_set: frozenset[str] | None = None,
    ) -> TeacherData:
        t = require_owned(self.db, Teacher, teacher_id, self.school_id)
        if fields_set is None:
            fields_set = frozenset()
        if "home_classroom_id" in fields_set and home_classroom_id is not None:
            require_owned(self.db, Classroom, home_classroom_id, self.school_id)
        if "full_name" in fields_set and full_name is not None:
            t.full_name = str(full_name).strip()
        if "email" in fields_set:
            t.email = None if email in (None, "") else str(email).strip() or None
        if "phone" in fields_set:
            t.phone = None if phone in (None, "") else str(phone).strip() or None
        if "home_classroom_id" in fields_set:
            t.home_classroom_id = home_classroom_id
        self.db.commit()
        self.db.refresh(t)
        return teacher_data(self._load_one(t.id))

    def delete(self, teacher_id: int) -> None:
        t = require_owned(self.db, Teacher, teacher_id, self.school_id)
        self.db.delete(t)
        self.db.commit()
