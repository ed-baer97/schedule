"""Assignment CRUD + upsert / group numbers."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    Classroom,
    ScheduleCell,
    SchoolClass,
    Subject,
    Teacher,
    TeachingAssignment,
)
from app.services.dto import AssignmentData, assignment_data
from app.services.errors import BadRequestError, NotFoundError
from app.services.tenancy import require_owned


class AssignmentCrudMixin:
    @staticmethod
    def _load_options() -> list:
        return [
            joinedload(TeachingAssignment.subject),
            joinedload(TeachingAssignment.teacher),
            joinedload(TeachingAssignment.school_class),
            joinedload(TeachingAssignment.preferred_classroom),
        ]

    def list(self, school_level: str | None = None) -> list[AssignmentData]:
        stmt = (
            select(TeachingAssignment)
            .options(*self._load_options())
            .join(SchoolClass, SchoolClass.id == TeachingAssignment.class_id)
            .where(TeachingAssignment.school_id == self.school_id)
            .order_by(SchoolClass.grade, SchoolClass.name)
        )
        if school_level:
            stmt = stmt.where(SchoolClass.school_level == school_level)
        return [assignment_data(a) for a in self.db.scalars(stmt).unique().all()]

    def get(self, assignment_id: int) -> AssignmentData:
        return assignment_data(self._get_orm(assignment_id))

    def _get_orm(self, assignment_id: int) -> TeachingAssignment:
        stmt = (
            select(TeachingAssignment)
            .options(*self._load_options())
            .where(
                TeachingAssignment.id == assignment_id,
                TeachingAssignment.school_id == self.school_id,
            )
        )
        a = self.db.execute(stmt).scalars().unique().one_or_none()
        if a is None:
            raise NotFoundError("Assignment not found")
        return a

    def _check_refs(
        self,
        *,
        subject_id: int | None = None,
        class_id: int | None = None,
        teacher_id: int | None = None,
        preferred_classroom_id: int | None = None,
    ) -> None:
        if subject_id is not None:
            require_owned(self.db, Subject, subject_id, self.school_id)
        if class_id is not None:
            require_owned(self.db, SchoolClass, class_id, self.school_id)
        if teacher_id is not None:
            require_owned(self.db, Teacher, teacher_id, self.school_id)
        if preferred_classroom_id is not None:
            require_owned(self.db, Classroom, preferred_classroom_id, self.school_id)

    def create(
        self,
        *,
        subject_id: int,
        class_id: int,
        hours_per_week: int,
        teacher_id: int | None = None,
        group_number: int | None = None,
        preferred_classroom_id: int | None = None,
        commit: bool = True,
    ) -> AssignmentData | TeachingAssignment:
        self._check_refs(
            subject_id=subject_id,
            class_id=class_id,
            teacher_id=teacher_id,
            preferred_classroom_id=preferred_classroom_id,
        )
        a = TeachingAssignment(
            school_id=self.school_id,
            subject_id=subject_id,
            teacher_id=teacher_id,
            class_id=class_id,
            hours_per_week=hours_per_week,
            group_number=group_number,
            preferred_classroom_id=preferred_classroom_id,
        )
        self.db.add(a)
        if commit:
            self.db.commit()
            return self.get(a.id)
        self.db.flush()
        return a

    def upsert_hours(
        self,
        *,
        subject_id: int,
        class_id: int,
        hours_per_week: int,
        teacher_id: int | None = None,
        match_null_teacher: bool = False,
        group_number: int | None = None,
        set_group: bool = False,
        commit: bool = False,
    ) -> tuple[TeachingAssignment, bool]:
        """Create or update hours for an assignment (import write-path)."""
        stmt = select(TeachingAssignment).where(
            TeachingAssignment.school_id == self.school_id,
            TeachingAssignment.subject_id == subject_id,
            TeachingAssignment.class_id == class_id,
        )
        if match_null_teacher:
            stmt = stmt.where(
                TeachingAssignment.teacher_id.is_(None),
                TeachingAssignment.group_number.is_(None),
            )
        else:
            stmt = stmt.where(TeachingAssignment.teacher_id == teacher_id)
        existing = self.db.scalars(stmt).first()
        if existing is not None:
            existing.hours_per_week = hours_per_week
            if set_group:
                existing.group_number = group_number
            if commit:
                self.db.commit()
            else:
                self.db.flush()
            return existing, False
        created = self.create(
            subject_id=subject_id,
            class_id=class_id,
            hours_per_week=hours_per_week,
            teacher_id=teacher_id,
            group_number=group_number if set_group else None,
            commit=False,
        )
        assert isinstance(created, TeachingAssignment)
        if commit:
            self.db.commit()
        return created, True

    def set_group_numbers(
        self,
        assignment_ids: list[int],
        group_numbers: list[int | None],
        *,
        commit: bool = False,
    ) -> None:
        """Set group_number for assignments (sole write-path for group numbering)."""
        if len(assignment_ids) != len(group_numbers):
            raise BadRequestError("assignment_ids and group_numbers length mismatch")
        for aid, gnum in zip(assignment_ids, group_numbers):
            a = require_owned(self.db, TeachingAssignment, aid, self.school_id)
            a.group_number = gnum
        if commit:
            self.db.commit()
        else:
            self.db.flush()

    def update(
        self,
        assignment_id: int,
        *,
        subject_id: int | None = None,
        teacher_id: int | None = None,
        class_id: int | None = None,
        hours_per_week: int | None = None,
        group_number: int | None = None,
        preferred_classroom_id: int | None = None,
        clear_teacher: bool = False,
        clear_group: bool = False,
        clear_preferred_classroom: bool = False,
    ) -> AssignmentData:
        a = require_owned(self.db, TeachingAssignment, assignment_id, self.school_id)
        self._check_refs(
            subject_id=subject_id,
            class_id=class_id,
            teacher_id=teacher_id,
            preferred_classroom_id=preferred_classroom_id,
        )
        if subject_id is not None:
            a.subject_id = subject_id
        if class_id is not None:
            a.class_id = class_id
        if hours_per_week is not None:
            a.hours_per_week = hours_per_week
        if clear_teacher:
            a.teacher_id = None
        elif teacher_id is not None:
            a.teacher_id = teacher_id
        if clear_group:
            a.group_number = None
        elif group_number is not None:
            a.group_number = group_number
        if clear_preferred_classroom:
            a.preferred_classroom_id = None
        elif preferred_classroom_id is not None:
            a.preferred_classroom_id = preferred_classroom_id
        self.db.commit()
        return self.get(a.id)

    def set_teacher(
        self, assignment_id: int, teacher_id: int | None
    ) -> AssignmentData:
        a = require_owned(self.db, TeachingAssignment, assignment_id, self.school_id)
        if teacher_id is not None:
            require_owned(self.db, Teacher, teacher_id, self.school_id)
        a.teacher_id = teacher_id
        self.db.commit()
        return self.get(a.id)

    def delete(self, assignment_id: int) -> None:
        a = require_owned(self.db, TeachingAssignment, assignment_id, self.school_id)
        self.db.delete(a)
        self.db.commit()

    def _reassign_cells_and_delete(
        self, assignment: TeachingAssignment, target_assignment_id: int
    ) -> None:
        cells = list(
            self.db.scalars(
                select(ScheduleCell).where(ScheduleCell.assignment_id == assignment.id)
            ).all()
        )
        for cell in cells:
            cell.assignment_id = target_assignment_id
        if cells:
            self.db.flush()
        self.db.delete(assignment)

