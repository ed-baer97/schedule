"""Classroom catalog CRUD."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Classroom
from app.services.tenancy import require_owned


class ClassroomService:
    def __init__(self, db: Session, school_id: int):
        self.db = db
        self.school_id = school_id

    def list(self) -> list[Classroom]:
        stmt = (
            select(Classroom)
            .where(Classroom.school_id == self.school_id)
            .order_by(func.coalesce(Classroom.floor, 999), Classroom.number)
        )
        return list(self.db.scalars(stmt).all())

    def get(self, classroom_id: int) -> Classroom:
        return require_owned(self.db, Classroom, classroom_id, self.school_id)

    def create(
        self,
        *,
        number: str,
        name: str | None = None,
        capacity: int | None = None,
        classes_capacity: int = 1,
        floor: int | None = None,
        building: str | None = None,
        commit: bool = True,
    ) -> Classroom:
        c = Classroom(
            school_id=self.school_id,
            number=number.strip(),
            name=(name or "").strip() or None,
            capacity=capacity,
            classes_capacity=classes_capacity or 1,
            floor=floor,
            building=(building or "").strip() or None,
        )
        self.db.add(c)
        if commit:
            self.db.commit()
            self.db.refresh(c)
        else:
            self.db.flush()
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
        return (
            self.create(
                number=number,
                name=name,
                classes_capacity=classes_capacity,
                floor=floor,
                building=building,
                commit=commit,
            ),
            True,
        )

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
        fields_set: frozenset[str] | None = None,
    ) -> Classroom:
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
        self.db.commit()
        self.db.refresh(c)
        return c

    def delete(self, classroom_id: int) -> None:
        c = require_owned(self.db, Classroom, classroom_id, self.school_id)
        self.db.delete(c)
        self.db.commit()
