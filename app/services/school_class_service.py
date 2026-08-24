"""School class catalog CRUD and batch shift update."""
from __future__ import annotations

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, joinedload

from app.domain import grade_from_name
from app.models import Classroom, SchoolClass, Shift, TeachingAssignment
from app.services.dto import SchoolClassData, school_class_data
from app.services.errors import BadRequestError, NotFoundError
from app.services.schedule_service import ScheduleService
from app.services.tenancy import require_owned


class SchoolClassService:
    def __init__(self, db: Session, school_id: int):
        self.db = db
        self.school_id = school_id

    def _load_options(self) -> list:
        return [
            joinedload(SchoolClass.shift),
            joinedload(SchoolClass.home_classroom),
        ]

    def _load_list(self) -> list[SchoolClass]:
        stmt = (
            select(SchoolClass)
            .options(*self._load_options())
            .where(SchoolClass.school_id == self.school_id)
            .order_by(SchoolClass.grade, SchoolClass.name)
        )
        return list(self.db.execute(stmt).scalars().unique().all())

    def _load_one(self, class_id: int) -> SchoolClass:
        stmt = (
            select(SchoolClass)
            .options(*self._load_options())
            .where(SchoolClass.id == class_id, SchoolClass.school_id == self.school_id)
        )
        row = self.db.execute(stmt).scalars().unique().one_or_none()
        if row is None:
            raise NotFoundError("Class not found")
        return row

    def list(self) -> list[SchoolClassData]:
        return [school_class_data(c) for c in self._load_list()]

    def get(self, class_id: int) -> SchoolClassData:
        return school_class_data(self._load_one(class_id))

    def batch_update_shift(
        self, class_ids: list[int], shift_id: int | None
    ) -> list[SchoolClassData]:
        if not class_ids:
            raise BadRequestError("class_ids required")
        if shift_id is not None:
            require_owned(self.db, Shift, shift_id, self.school_id)
        self.db.execute(
            update(SchoolClass)
            .where(
                SchoolClass.id.in_(class_ids),
                SchoolClass.school_id == self.school_id,
            )
            .values(shift_id=shift_id)
        )
        self.db.commit()
        return self.list()

    def create(
        self,
        *,
        name: str,
        school_level: str,
        shift_id: int | None = None,
        home_classroom_id: int | None = None,
        students_count: int | None = None,
        commit: bool = True,
    ) -> SchoolClassData | SchoolClass:
        name = name.strip()
        if shift_id is not None:
            require_owned(self.db, Shift, shift_id, self.school_id)
        if home_classroom_id is not None:
            require_owned(self.db, Classroom, home_classroom_id, self.school_id)
        sc = SchoolClass(
            school_id=self.school_id,
            name=name,
            grade=grade_from_name(name),
            school_level=school_level,
            shift_id=shift_id,
            home_classroom_id=home_classroom_id,
            students_count=students_count,
        )
        self.db.add(sc)
        if commit:
            self.db.commit()
            self.db.refresh(sc)
            return school_class_data(self._load_one(sc.id))
        self.db.flush()
        return sc

    def find_by_name(self, name: str) -> SchoolClass | None:
        return self.db.scalars(
            select(SchoolClass).where(
                SchoolClass.school_id == self.school_id,
                SchoolClass.name == name.strip(),
            )
        ).first()

    def ensure(
        self, name: str, *, school_level: str, commit: bool = False
    ) -> tuple[SchoolClass, bool]:
        existing = self.find_by_name(name)
        if existing is not None:
            return existing, False
        created = self.create(name=name, school_level=school_level, commit=False)
        assert isinstance(created, SchoolClass)
        if commit:
            self.db.commit()
        return created, True

    def update(
        self,
        class_id: int,
        *,
        name: str | None = None,
        school_level: str | None = None,
        shift_id: int | None = None,
        home_classroom_id: int | None = None,
        students_count: int | None = None,
        fields_set: frozenset[str] | None = None,
    ) -> SchoolClassData:
        sc = require_owned(self.db, SchoolClass, class_id, self.school_id)
        if fields_set is None:
            fields_set = frozenset()
        if "shift_id" in fields_set and shift_id is not None:
            require_owned(self.db, Shift, shift_id, self.school_id)
        if "home_classroom_id" in fields_set and home_classroom_id is not None:
            require_owned(self.db, Classroom, home_classroom_id, self.school_id)
        if "name" in fields_set and name is not None:
            sc.name = str(name).strip()
            sc.grade = grade_from_name(sc.name)
        if "school_level" in fields_set and school_level is not None:
            sc.school_level = school_level
        if "shift_id" in fields_set:
            sc.shift_id = shift_id
        if "home_classroom_id" in fields_set:
            sc.home_classroom_id = home_classroom_id
        if "students_count" in fields_set:
            sc.students_count = students_count
        self.db.commit()
        self.db.refresh(sc)
        return school_class_data(self._load_one(sc.id))

    def delete(self, class_id: int) -> None:
        sc = require_owned(self.db, SchoolClass, class_id, self.school_id)
        # Cells first (FK to assignment + class), then assignments, then class.
        # Without this, SQLAlchemy nullifies TeachingAssignment.class_id → NOT NULL.
        ScheduleService(self.db, self.school_id).delete_cells(
            class_id=class_id, commit=False
        )
        self.db.execute(
            delete(TeachingAssignment).where(
                TeachingAssignment.class_id == class_id,
                TeachingAssignment.school_id == self.school_id,
            )
        )
        self.db.delete(sc)
        self.db.commit()
