"""Classroom catalog CRUD."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import Classroom, Subject, Teacher
from app.services.dto import ClassroomData, classroom_data
from app.services.errors import BadRequestError
from app.services.tenancy import require_owned


class ClassroomService:
    def __init__(self, db: Session, school_id: int):
        self.db = db
        self.school_id = school_id

    def _load(self, classroom_id: int) -> Classroom:
        stmt = (
            select(Classroom)
            .options(
                joinedload(Classroom.subject),
                selectinload(Classroom.teachers),
            )
            .where(
                Classroom.id == classroom_id,
                Classroom.school_id == self.school_id,
            )
        )
        row = self.db.execute(stmt).scalars().unique().one_or_none()
        if row is None:
            from app.services.errors import NotFoundError

            raise NotFoundError("Classroom not found")
        return row

    def _validate_subject_fields(
        self, subject_id: int | None, is_exclusive: bool
    ) -> None:
        if is_exclusive and subject_id is None:
            raise BadRequestError(
                "Фиксированный кабинет должен быть привязан к предмету"
            )
        if subject_id is not None:
            require_owned(self.db, Subject, subject_id, self.school_id)

    def _sync_teachers(self, classroom_id: int, teacher_ids: list[int]) -> None:
        wanted = list(dict.fromkeys(int(tid) for tid in teacher_ids))
        for tid in wanted:
            require_owned(self.db, Teacher, tid, self.school_id)
        wanted_set = set(wanted)

        current = self.db.scalars(
            select(Teacher).where(
                Teacher.school_id == self.school_id,
                Teacher.home_classroom_id == classroom_id,
            )
        ).all()
        for teacher in current:
            if teacher.id not in wanted_set:
                teacher.home_classroom_id = None

        missing = wanted_set - {t.id for t in current}
        if missing:
            to_assign = self.db.scalars(
                select(Teacher).where(
                    Teacher.school_id == self.school_id,
                    Teacher.id.in_(missing),
                )
            ).all()
            for teacher in to_assign:
                teacher.home_classroom_id = classroom_id

    def list(self) -> list[ClassroomData]:
        stmt = (
            select(Classroom)
            .options(
                joinedload(Classroom.subject),
                selectinload(Classroom.teachers),
            )
            .where(Classroom.school_id == self.school_id)
            .order_by(func.coalesce(Classroom.floor, 999), Classroom.number)
        )
        return [
            classroom_data(c)
            for c in self.db.execute(stmt).scalars().unique().all()
        ]

    def get(self, classroom_id: int) -> ClassroomData:
        return classroom_data(self._load(classroom_id))

    def create(
        self,
        *,
        number: str,
        name: str | None = None,
        capacity: int | None = None,
        classes_capacity: int = 1,
        floor: int | None = None,
        building: str | None = None,
        subject_id: int | None = None,
        is_exclusive: bool = False,
        teacher_ids: list[int] | None = None,
        commit: bool = True,
    ) -> ClassroomData | Classroom:
        self._validate_subject_fields(subject_id, is_exclusive)
        c = Classroom(
            school_id=self.school_id,
            number=number.strip(),
            name=(name or "").strip() or None,
            capacity=capacity,
            classes_capacity=classes_capacity or 1,
            floor=floor,
            building=(building or "").strip() or None,
            subject_id=subject_id,
            is_exclusive=bool(is_exclusive) if subject_id else False,
        )
        self.db.add(c)
        self.db.flush()
        if teacher_ids:
            self._sync_teachers(c.id, teacher_ids)
        if commit:
            self.db.commit()
            return classroom_data(self._load(c.id))
        return c

    def find_by_number(self, number: str) -> Classroom | None:
        n = number.strip()
        return self.db.scalars(
            select(Classroom).where(
                Classroom.school_id == self.school_id, Classroom.number == n
            )
        ).first()

    def ensure(
        self,
        *,
        number: str,
        name: str | None = None,
        classes_capacity: int = 1,
        floor: int | None = None,
        building: str | None = None,
        commit: bool = False,
    ) -> tuple[Classroom, bool]:
        existing = self.find_by_number(number)
        if existing is not None:
            return existing, False
        created = self.create(
            number=number,
            name=name,
            classes_capacity=classes_capacity,
            floor=floor,
            building=building,
            commit=False,
        )
        assert isinstance(created, Classroom)
        if commit:
            self.db.commit()
        return created, True

    def update(
        self,
        classroom_id: int,
        *,
        number: str | None = None,
        name: str | None = None,
        capacity: int | None = None,
        classes_capacity: int | None = None,
        floor: int | None = None,
        building: str | None = None,
        subject_id: int | None = None,
        is_exclusive: bool | None = None,
        teacher_ids: list[int] | None = None,
        fields_set: frozenset[str] | None = None,
    ) -> ClassroomData:
        c = require_owned(self.db, Classroom, classroom_id, self.school_id)
        if fields_set is None:
            fields_set = frozenset()
        if "number" in fields_set and number is not None:
            c.number = str(number).strip()
        if "name" in fields_set:
            c.name = (name or "").strip() or None
        if "capacity" in fields_set:
            c.capacity = capacity
        if "classes_capacity" in fields_set and classes_capacity is not None:
            c.classes_capacity = int(classes_capacity)
        if "floor" in fields_set:
            c.floor = floor
        if "building" in fields_set:
            c.building = (building or "").strip() or None

        new_subject_id = c.subject_id
        new_exclusive = bool(c.is_exclusive)
        if "subject_id" in fields_set:
            new_subject_id = subject_id
        if "is_exclusive" in fields_set and is_exclusive is not None:
            new_exclusive = bool(is_exclusive)
        if new_subject_id is None:
            new_exclusive = False
        self._validate_subject_fields(new_subject_id, new_exclusive)
        if "subject_id" in fields_set:
            c.subject_id = new_subject_id
        if "is_exclusive" in fields_set or "subject_id" in fields_set:
            c.is_exclusive = new_exclusive

        if "teacher_ids" in fields_set and teacher_ids is not None:
            self._sync_teachers(classroom_id, teacher_ids)

        self.db.commit()
        return classroom_data(self._load(classroom_id))

    def delete(self, classroom_id: int) -> None:
        c = require_owned(self.db, Classroom, classroom_id, self.school_id)
        for teacher in self.db.scalars(
            select(Teacher).where(
                Teacher.school_id == self.school_id,
                Teacher.home_classroom_id == classroom_id,
            )
        ):
            teacher.home_classroom_id = None
        self.db.delete(c)
        self.db.commit()
