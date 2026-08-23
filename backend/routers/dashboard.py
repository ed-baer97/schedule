"""Dashboard statistics."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.models import School
from app.services.dashboard_service import DashboardService
from backend.deps import get_current_school, get_db
from backend.schemas.dashboard import DashboardStatsOut

router = APIRouter()


@router.get("/stats", response_model=DashboardStatsOut)
def get_stats(
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> DashboardStatsOut:
    data = DashboardService(db, school.id).stats()
    return DashboardStatsOut(
        teachers_count=data.teachers_count,
        classes_count=data.classes_count,
        subjects_count=data.subjects_count,
        classrooms_count=data.classrooms_count,
        elementary_classes=data.elementary_classes,
        secondary_classes=data.secondary_classes,
        elementary_assignments=data.elementary_assignments,
        secondary_assignments=data.secondary_assignments,
        elementary_scheduled=data.elementary_scheduled,
        secondary_scheduled=data.secondary_scheduled,
    )
