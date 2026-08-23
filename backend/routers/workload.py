"""Workload (hours per class x subject) API."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.models import School
from app.services.assignment_service import AssignmentService
from app.services.errors import ServiceError
from backend.deps import get_current_school, get_db
from backend.http_errors import raise_http
from backend.schemas.workload import (
    SchoolClassBrief,
    SubjectBrief,
    WorkloadCellOut,
    WorkloadCellUpdate,
    WorkloadOut,
)

router = APIRouter()


@router.get("/", response_model=WorkloadOut)
def get_workload(
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
    school_level: str = Query("elementary", pattern="^(elementary|secondary)$"),
) -> WorkloadOut:
    data = AssignmentService(db, school.id).get_workload(school_level)
    return WorkloadOut(
        school_level=data.school_level,
        classes=[SchoolClassBrief.model_validate(c) for c in data.classes],
        subjects=[SubjectBrief.model_validate(s) for s in data.subjects],
        cells=[
            WorkloadCellOut(class_id=c, subject_id=s, hours=h)
            for c, s, h in data.cells
        ],
    )


@router.put("/cell", response_model=dict)
def update_workload_cell(
    body: WorkloadCellUpdate,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> dict:
    try:
        AssignmentService(db, school.id).update_workload_cell(
            body.class_id, body.subject_id, body.hours
        )
    except ServiceError as exc:
        raise_http(exc)
    return {"status": "ok"}
