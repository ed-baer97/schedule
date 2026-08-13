"""Dashboard statistics (mirrors Flask main.index)."""
from fastapi import APIRouter, Depends
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

from backend.deps import get_db
from backend.schemas.dashboard import DashboardStatsOut

router = APIRouter()


@router.get("/stats", response_model=DashboardStatsOut)
def get_stats(db: Session = Depends(get_db)) -> DashboardStatsOut:
    teachers_count = db.scalar(select(func.count()).select_from(Teacher)) or 0
    classes_count = db.scalar(select(func.count()).select_from(SchoolClass)) or 0
    subjects_count = db.scalar(select(func.count()).select_from(Subject)) or 0
    classrooms_count = db.scalar(select(func.count()).select_from(Classroom)) or 0

    el_ids = list(
        db.scalars(
            select(SchoolClass.id).where(SchoolClass.school_level == "elementary")
        ).all()
    )
    sec_ids = list(
        db.scalars(
            select(SchoolClass.id).where(SchoolClass.school_level == "secondary")
        ).all()
    )

    def _count_assignments(class_ids: list[int]) -> int:
        if not class_ids:
            return 0
        return (
            db.scalar(
                select(func.count())
                .select_from(TeachingAssignment)
                .where(TeachingAssignment.class_id.in_(class_ids))
            )
            or 0
        )

    def _count_scheduled(class_ids: list[int]) -> int:
        if not class_ids:
            return 0
        return (
            db.scalar(
                select(func.count())
                .select_from(ScheduleCell)
                .where(ScheduleCell.class_id.in_(class_ids))
            )
            or 0
        )

    return DashboardStatsOut(
        teachers_count=int(teachers_count),
        classes_count=int(classes_count),
        subjects_count=int(subjects_count),
        classrooms_count=int(classrooms_count),
        elementary_classes=len(el_ids),
        secondary_classes=len(sec_ids),
        elementary_assignments=_count_assignments(el_ids),
        secondary_assignments=_count_assignments(sec_ids),
        elementary_scheduled=_count_scheduled(el_ids),
        secondary_scheduled=_count_scheduled(sec_ids),
    )
