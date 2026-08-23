"""Background job status API."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models import School, User
from app.services.errors import ServiceError
from app.services.job_service import JobService
from backend.deps import get_current_school, get_current_user, get_db
from backend.http_errors import raise_http

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
    try:
        data = JobService(db, school.id).get(job_id)
    except ServiceError as exc:
        raise_http(exc)
    return JobOut(
        id=data.id,
        kind=data.kind,
        status=data.status,
        progress=data.progress,
        result=data.result,
        error=data.error,
    )
