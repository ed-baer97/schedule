"""Subject catalog CRUD (not teaching assignments)."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models import Classroom, SchoolClass, Subject, TeachingAssignment
from app.services.dto import SubjectData, subject_data
from app.services.errors import NotFoundError
from app.services.tenancy import require_owned


@dataclass
class SubjectColorData:
    id: int
    display_color: str


class SubjectService:
    def __init__(self, db: Session, school_id: int):
        self.db = db
        self.school_id = school_id

    def _load_one(self, subject_id: int) -> Subject:
        stmt = (
            select(Subject)
            .options(joinedload(Subject.default_classroom))
            .where(Subject.id == subject_id, Subject.school_id == self.school_id)
        )
        row = self.db.execute(stmt).scalars().unique().one_or_none()
        if row is None:
            raise NotFoundError("Subject not found")
        return row

    def list(self, school_level: str | None = None) -> list[SubjectData]:
        if school_level in ("elementary", "secondary"):
            ids = list(
                self.db.scalars(
                    select(TeachingAssignment.subject_id)
                    .join(SchoolClass, SchoolClass.id == TeachingAssignment.class_id)
                    .where(
                        SchoolClass.school_level == school_level,
                        SchoolClass.school_id == self.school_id,
                    )
                    .distinct()
                ).all()
            )
            if not ids:
                return []
            stmt = (
                select(Subject)
                .where(Subject.id.in_(ids), Subject.school_id == self.school_id)
                .options(joinedload(Subject.default_classroom))
                .order_by(Subject.name)
            )
            return [subject_data(s) for s in self.db.scalars(stmt).unique().all()]
        stmt = (
            select(Subject)
            .where(Subject.school_id == self.school_id)
            .options(joinedload(Subject.default_classroom))
            .order_by(Subject.name)
        )
        return [subject_data(s) for s in self.db.scalars(stmt).unique().all()]

    def get(self, subject_id: int) -> SubjectData:
        return subject_data(self._load_one(subject_id))

    def create(
        self,
        *,
        name: str,
        color: str,
        requires_fixed_classroom: bool = False,
        default_classroom_id: int | None = None,
        commit: bool = True,
    ) -> SubjectData | Subject:
        if default_classroom_id is not None:
            require_owned(self.db, Classroom, default_classroom_id, self.school_id)
        s = Subject(
            school_id=self.school_id,
            name=name.strip(),
            color=color,
            requires_fixed_classroom=requires_fixed_classroom,
            default_classroom_id=default_classroom_id,
        )
        self.db.add(s)
        if commit:
            self.db.commit()
            self.db.refresh(s)
            return subject_data(self._load_one(s.id))
        self.db.flush()
        return s

    def find_by_name(self, name: str) -> Subject | None:
        return self.db.scalars(
            select(Subject).where(
                Subject.school_id == self.school_id, Subject.name == name.strip()
            )
        ).first()

    def ensure(
        self, name: str, *, color: str | None = None, commit: bool = False
    ) -> tuple[Subject, bool]:
        existing = self.find_by_name(name)
        if existing is not None:
            return existing, False
        if color is None:
            count = (
                self.db.scalar(
                    select(func.count())
                    .select_from(Subject)
                    .where(Subject.school_id == self.school_id)
                )
                or 0
            )
            palette = Subject.COLOR_PALETTE
            color = palette[int(count) % len(palette)]
        created = self.create(name=name, color=color, commit=False)
        assert isinstance(created, Subject)
        if commit:
            self.db.commit()
        return created, True

    def update(
        self,
        subject_id: int,
        *,
        name: str | None = None,
        color: str | None = None,
        requires_fixed_classroom: bool | None = None,
        default_classroom_id: int | None = None,
        fields_set: frozenset[str] | None = None,
    ) -> SubjectData:
        s = require_owned(self.db, Subject, subject_id, self.school_id)
        if fields_set is None:
            fields_set = frozenset()
        if "default_classroom_id" in fields_set and default_classroom_id is not None:
            require_owned(self.db, Classroom, default_classroom_id, self.school_id)
        if "name" in fields_set and name is not None:
            s.name = str(name).strip()
        if "color" in fields_set and color is not None:
            s.color = color
        if "requires_fixed_classroom" in fields_set and requires_fixed_classroom is not None:
            s.requires_fixed_classroom = bool(requires_fixed_classroom)
        if "default_classroom_id" in fields_set:
            s.default_classroom_id = default_classroom_id
        self.db.commit()
        self.db.refresh(s)
        return subject_data(self._load_one(s.id))

    def set_color(self, subject_id: int, color: str) -> SubjectColorData:
        s = require_owned(self.db, Subject, subject_id, self.school_id)
        s.color = color
        self.db.commit()
        self.db.refresh(s)
        return SubjectColorData(id=s.id, display_color=s.display_color)

    @staticmethod
    def color_palette() -> list[str]:
        return list(Subject.COLOR_PALETTE)

    def delete(self, subject_id: int) -> None:
        s = require_owned(self.db, Subject, subject_id, self.school_id)
        self.db.delete(s)
        self.db.commit()
