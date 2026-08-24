"""Background job status API."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models import School, User
from app.services.job_service import JobService
from backend.deps import get_current_school, get_current_user, get_db

router = APIRouter()


class JobOut(BaseModel):
    id: int
    kind: str
    status: str
    progress: dict | None = None
    result: dict | None = None
    error: str | None = None

    model_config = {"from_attributes": True}


@router.get("/{job_id}", response_model=JobOut)
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
    _: User = Depends(get_current_user),
) -> JobOut:
    data = JobService(db, school.id).get(job_id)
    return JobOut(
        id=data.id,
        kind=data.kind,
        status=data.status,
        progress=data.progress,
        result=data.result,
        error=data.error,
    )
