"""Workload hours view and cell update."""
from __future__ import annotations

from sqlalchemy import select

from app.models import SchoolClass, Subject, TeachingAssignment
from app.services.assignment.types import WorkloadViewData
from app.services.dto import school_class_brief, subject_brief
from app.services.errors import BadRequestError
from app.services.tenancy import require_owned


class AssignmentWorkloadMixin:
    def get_workload(self, school_level: str) -> WorkloadViewData:
        classes = list(
            self.db.scalars(
                select(SchoolClass)
                .where(
                    SchoolClass.school_id == self.school_id,
                    SchoolClass.school_level == school_level,
                )
                .order_by(SchoolClass.grade, SchoolClass.name)
            ).all()
        )
        subjects = list(
            self.db.scalars(
                select(Subject)
                .where(Subject.school_id == self.school_id)
                .order_by(Subject.name)
            ).all()
        )
        assignments = list(
            self.db.scalars(
                select(TeachingAssignment)
                .join(SchoolClass, SchoolClass.id == TeachingAssignment.class_id)
                .where(
                    TeachingAssignment.school_id == self.school_id,
                    SchoolClass.school_level == school_level,
                )
            ).all()
        )
        totals: dict[tuple[int, int], int] = {}
        for a in assignments:
            key = (a.class_id, a.subject_id)
            totals[key] = totals.get(key, 0) + int(a.hours_per_week or 0)
        cells = [(k[0], k[1], h) for k, h in sorted(totals.items())]
        return WorkloadViewData(
            school_level=school_level,
            classes=[school_class_brief(c) for c in classes],
            subjects=[subject_brief(s) for s in subjects],
            cells=cells,
        )

    def update_workload_cell(
        self, class_id: int, subject_id: int, hours: int
    ) -> None:
        if hours < 0:
            raise BadRequestError("hours must be >= 0")
        require_owned(self.db, SchoolClass, class_id, self.school_id)
        require_owned(self.db, Subject, subject_id, self.school_id)

        assignment = self.db.scalars(
            select(TeachingAssignment).where(
                TeachingAssignment.school_id == self.school_id,
                TeachingAssignment.class_id == class_id,
                TeachingAssignment.subject_id == subject_id,
                TeachingAssignment.teacher_id.is_(None),
            )
        ).first()

        if hours == 0:
            if assignment:
                self.db.delete(assignment)
                self.db.commit()
            return

        if assignment:
            assignment.hours_per_week = hours
        else:
            self.db.add(
                TeachingAssignment(
                    school_id=self.school_id,
                    class_id=class_id,
                    subject_id=subject_id,
                    hours_per_week=hours,
                    teacher_id=None,
                )
            )
        self.db.commit()

