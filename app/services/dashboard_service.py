"""School dashboard statistics."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Classroom,
    ScheduleCell,
    SchoolClass,
    Subject,
    Teacher,
    TeachingAssignment,
)


@dataclass
class DashboardStatsData:
    teachers_count: int
    classes_count: int
    subjects_count: int
    classrooms_count: int
    elementary_classes: int
    secondary_classes: int
    elementary_assignments: int
    secondary_assignments: int
    elementary_scheduled: int
    secondary_scheduled: int


class DashboardService:
    def __init__(self, db: Session, school_id: int):
        self.db = db
        self.school_id = school_id

    def stats(self) -> DashboardStatsData:
        sid = self.school_id
        teachers_count = (
            self.db.scalar(
                select(func.count()).select_from(Teacher).where(Teacher.school_id == sid)
            )
            or 0
        )
        classes_count = (
            self.db.scalar(
                select(func.count())
                .select_from(SchoolClass)
                .where(SchoolClass.school_id == sid)
            )
            or 0
        )
        subjects_count = (
            self.db.scalar(
                select(func.count()).select_from(Subject).where(Subject.school_id == sid)
            )
            or 0
        )
        classrooms_count = (
            self.db.scalar(
                select(func.count())
                .select_from(Classroom)
                .where(Classroom.school_id == sid)
            )
            or 0
        )

        el_ids = list(
            self.db.scalars(
                select(SchoolClass.id).where(
                    SchoolClass.school_id == sid,
                    SchoolClass.school_level == "elementary",
                )
            ).all()
        )
        sec_ids = list(
            self.db.scalars(
                select(SchoolClass.id).where(
                    SchoolClass.school_id == sid,
                    SchoolClass.school_level == "secondary",
                )
            ).all()
        )

        return DashboardStatsData(
            teachers_count=int(teachers_count),
            classes_count=int(classes_count),
            subjects_count=int(subjects_count),
            classrooms_count=int(classrooms_count),
            elementary_classes=len(el_ids),
            secondary_classes=len(sec_ids),
            elementary_assignments=self._count_assignments(el_ids),
            secondary_assignments=self._count_assignments(sec_ids),
            elementary_scheduled=self._count_scheduled(el_ids),
            secondary_scheduled=self._count_scheduled(sec_ids),
        )

    def _count_assignments(self, class_ids: list[int]) -> int:
        if not class_ids:
            return 0
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(TeachingAssignment)
                .where(
                    TeachingAssignment.school_id == self.school_id,
                    TeachingAssignment.class_id.in_(class_ids),
                )
            )
            or 0
        )

    def _count_scheduled(self, class_ids: list[int]) -> int:
        if not class_ids:
            return 0
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(ScheduleCell)
                .where(
                    ScheduleCell.school_id == self.school_id,
                    ScheduleCell.class_id.in_(class_ids),
                )
            )
            or 0
        )
