"""Background job status API."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models import Job, School, User
from backend.deps import get_current_school, get_current_user, get_db, school_owned

router = APIRouter()


class JobOut(BaseModel):
    id: int
    kind: str
    status: str
    progress: dict | None = None
    result: dict | None = None
    error: str | None = None

    model_config = {"from_attributes": True}


def _parse_json(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {"value": data}
    except json.JSONDecodeError:
        return {"raw": raw}


@router.get("/{job_id}", response_model=JobOut)
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
    _: User = Depends(get_current_user),
) -> JobOut:
    job = school_owned(db, Job, job_id, school.id)
    return JobOut(
        id=job.id,
        kind=job.kind,
        status=job.status,
        progress=_parse_json(job.progress),
        result=_parse_json(job.result),
        error=job.error,
    )
