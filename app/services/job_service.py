"""Background job status and enqueue for school-scoped auto-schedule tasks."""
from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Config
from app.models import Job, SchoolClass, Shift, Teacher
from app.models.job import (
    JOB_ACTIVE_STATUSES,
    JOB_CANCELLED,
    JOB_CANCELLING,
    JOB_DONE,
    JOB_FAILED,
    JOB_PENDING,
)
from app.services.errors import BadRequestError, ConflictError
from app.services.job_dispatch import dispatch_auto_job, revoke_auto_job
from app.services.tenancy import require_owned


@dataclass
class JobStatusData:
    id: int
    kind: str
    status: str
    progress: dict | None
    result: dict | None
    error: str | None


def _parse_json(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {"value": data}
    except json.JSONDecodeError:
        return {"raw": raw}


class JobService:
    def __init__(self, db: Session, school_id: int):
        self.db = db
        self.school_id = school_id

    def get(self, job_id: int) -> JobStatusData:
        job = require_owned(self.db, Job, job_id, self.school_id)
        return JobStatusData(
            id=job.id,
            kind=job.kind,
            status=job.status,
            progress=_parse_json(job.progress),
            result=_parse_json(job.result),
            error=job.error,
        )

    def enqueue_auto(
        self,
        *,
        kind: str,
        payload: dict,
        created_by_id: int,
        dispatch: bool = True,
    ) -> dict:
        """Create a Job row and optionally dispatch via job_dispatch port."""
        body = dict(payload)
        shift_id = body.get("shift_id")
        if shift_id is not None:
            require_owned(self.db, Shift, int(shift_id), self.school_id)
        teacher_id = body.get("teacher_id")
        if teacher_id is not None:
            require_owned(self.db, Teacher, int(teacher_id), self.school_id)
        class_id = body.get("class_id")
        if class_id is not None:
            require_owned(self.db, SchoolClass, int(class_id), self.school_id)

        active = self.db.scalars(
            select(Job).where(
                Job.school_id == self.school_id,
                Job.status.in_(JOB_ACTIVE_STATUSES),
            )
        ).first()
        if active is not None:
            raise ConflictError(
                f"Уже выполняется задача #{active.id}. Дождитесь завершения."
            )

        if "time_limit_sec" not in body:
            body["time_limit_sec"] = Config.SOLVER_TIME_LIMIT_SEC
        else:
            body["time_limit_sec"] = min(
                float(body["time_limit_sec"]), float(Config.SOLVER_TIME_LIMIT_SEC)
            )

        job = Job(
            school_id=self.school_id,
            kind=kind,
            status=JOB_PENDING,
            progress=json.dumps(body, ensure_ascii=False),
            created_by_id=created_by_id,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)

        if dispatch:
            dispatch_auto_job(job.id)
            self.db.refresh(job)

        return {"job_id": job.id, "status": JOB_PENDING}

    def cancel(self, job_id: int) -> JobStatusData:
        """Ask a pending/running auto-job to stop. Cooperative: CP-SAT StopSearch."""
        job = require_owned(self.db, Job, job_id, self.school_id)
        if job.status in (JOB_DONE, JOB_FAILED, JOB_CANCELLED):
            raise BadRequestError("Задача уже завершена, останавливать нечего.")

        payload = _parse_json(job.progress) or {}
        celery_id = job.celery_task_id
        if job.status == JOB_PENDING:
            job.status = JOB_CANCELLED
            job.result = json.dumps(
                {"type": "cancelled", "count": 0, "message": "Остановлено"},
                ensure_ascii=False,
            )
            job.progress = json.dumps(
                {**payload, "message": "Остановлено"},
                ensure_ascii=False,
            )
        else:
            job.status = JOB_CANCELLING
            job.progress = json.dumps(
                {**payload, "message": "Остановка…"},
                ensure_ascii=False,
            )
        self.db.commit()
        self.db.refresh(job)
        if celery_id:
            revoke_auto_job(str(celery_id))
        return self.get(job_id)
