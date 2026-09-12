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
from app.services.report_service import ExportFile, unique_sheet_name
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
        """Excel: по листу на предмет — учителя × классы, в ячейках часы."""
        assignments = list(
            self.db.execute(
                select(TeachingAssignment)
                .options(
                    joinedload(TeachingAssignment.subject),
                    joinedload(TeachingAssignment.teacher),
                    joinedload(TeachingAssignment.school_class),
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

        # subject_id -> subject_name, class_id -> class meta, teacher_id -> name,
        # hours[(subject_id, teacher_id, class_id)]
        subject_names: dict[int, str] = {}
        class_meta: dict[int, tuple[int, str]] = {}  # id -> (grade, name)
        teacher_names: dict[int, str] = {}
        hours: dict[tuple[int, int, int], int] = defaultdict(int)

        for assignment in assignments:
            h = int(assignment.hours_per_week or 0)
            if h <= 0 or assignment.teacher_id is None:
                continue
            sid = int(assignment.subject_id)
            tid = int(assignment.teacher_id)
            cid = int(assignment.class_id)
            subject_names[sid] = assignment.subject.name
            teacher_names[tid] = assignment.teacher.full_name
            school_class = assignment.school_class
            class_meta[cid] = (int(school_class.grade), school_class.name)
            hours[(sid, tid, cid)] += h

        workbook = Workbook()
        used_sheet_names: set[str] = set()

        if not subject_names:
            empty = workbook.active
            empty.title = unique_sheet_name("Нет данных", used_sheet_names)
            empty.cell(1, 1, "Нет назначений с часами")
            empty["A1"].font = _CELL_FONT
        else:
            first = True
            for sid, subject_name in sorted(
                subject_names.items(), key=lambda item: item[1].casefold()
            ):
                teacher_ids = sorted(
                    {tid for (s, tid, _cid) in hours if s == sid},
                    key=lambda tid: teacher_names[tid].casefold(),
                )
                class_ids = sorted(
                    {cid for (s, _tid, cid) in hours if s == sid},
                    key=lambda cid: class_meta[cid],
                )
                sheet_name = unique_sheet_name(subject_name, used_sheet_names)
                if first:
                    ws = workbook.active
                    ws.title = sheet_name
                    first = False
                else:
                    ws = workbook.create_sheet(sheet_name)

                # Title row with subject name inside the sheet
                title_cell = ws.cell(1, 1, subject_name)
                title_cell.font = Font(bold=True, size=14, color="14201A", name="Calibri")
                last_col = 2 + len(class_ids)  # №, ФИО, classes..., Итого
                if last_col > 1:
                    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)

                headers = ["№", "ФИО", *[class_meta[cid][1] for cid in class_ids], "Итого"]
                for col, header in enumerate(headers, start=1):
                    cell = ws.cell(2, col, header)
                    cell.fill = _HEADER_FILL
                    cell.font = _HEADER_FONT
                    cell.alignment = _HEADER_ALIGN
                    cell.border = _GRID

                for row_idx, tid in enumerate(teacher_ids, start=3):
                    row_hours = [hours.get((sid, tid, cid), 0) for cid in class_ids]
                    total = sum(row_hours)
                    values: list[object] = [
                        row_idx - 2,
                        teacher_names[tid],
                        *[h if h > 0 else None for h in row_hours],
                        total if total > 0 else 0,
                    ]
                    for col, value in enumerate(values, start=1):
                        cell = ws.cell(row_idx, col, value)
                        cell.border = _GRID
                        if col == 1:
                            cell.font = _CELL_FONT
                            cell.alignment = _NUM_ALIGN
                        elif col == 2:
                            cell.font = _CELL_FONT
                            cell.alignment = _CELL_ALIGN
                        elif col == last_col:
                            cell.font = _TOTAL_FONT
                            cell.alignment = _NUM_ALIGN
                        else:
                            cell.font = _CELL_FONT
                            cell.alignment = _NUM_ALIGN

                ws.column_dimensions["A"].width = 5
                ws.column_dimensions["B"].width = 32
                for col in range(3, last_col):
                    ws.column_dimensions[get_column_letter(col)].width = 8
                ws.column_dimensions[get_column_letter(last_col)].width = 10
                ws.freeze_panes = "C3"
                ws.auto_filter.ref = f"A2:{get_column_letter(last_col)}{max(2, 2 + len(teacher_ids))}"
                ws.row_dimensions[1].height = 22
                ws.row_dimensions[2].height = 28

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
