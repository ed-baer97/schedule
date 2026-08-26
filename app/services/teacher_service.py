"""Teacher catalog CRUD."""
from __future__ import annotations

from collections import defaultdict

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
from app.services.tenancy import require_owned


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
