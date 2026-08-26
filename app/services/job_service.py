"""Background job status and enqueue for school-scoped auto-schedule tasks."""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
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

# Celery worker heartbeat is ~0.3s; no pulse → process was killed.
_STALE_RUNNING_SEC = 120
# Pending should be dispatched immediately; leftover rows after a crash.
_STALE_PENDING_SEC = 30
_INTERRUPTED_MSG = "Процесс составления был прерван. Запустите заново."


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _naive(ts: datetime | None) -> datetime | None:
    if ts is None:
        return None
    if ts.tzinfo is not None:
        return ts.replace(tzinfo=None)
    return ts


def _is_stale(job: Job, now: datetime, stale_sec: int) -> bool:
    ts = _naive(job.updated_at) or _naive(job.created_at)
    if ts is None:
        return True
    return (now - ts) > timedelta(seconds=stale_sec)


def _in_process_thread_alive(job_id: int) -> bool:
    name = f"auto-job-{job_id}"
    return any(t.is_alive() and t.name == name for t in threading.enumerate())


def _has_celery_id(job: Job) -> bool:
    return bool(job.celery_task_id)


def worker_looks_dead(job: Job, *, now: datetime | None = None) -> bool:
    """True when the row is active but no worker can still be running it."""
    now = now or _utc_now()
    if job.status == JOB_PENDING:
        return _is_stale(job, now, _STALE_PENDING_SEC)
    if _has_celery_id(job):
        return _is_stale(job, now, _STALE_RUNNING_SEC)
    return not _in_process_thread_alive(job.id)


def _mark_interrupted(job: Job, message: str = _INTERRUPTED_MSG) -> None:
    payload = _parse_json(job.progress) or {}
    job.status = JOB_FAILED
    job.error = message
    job.result = json.dumps(
        {"type": "interrupted", "message": message},
        ensure_ascii=False,
    )
    job.progress = json.dumps({**payload, "message": message}, ensure_ascii=False)
    job.updated_at = _utc_now()


def abandon_in_process_jobs(db: Session) -> int:
    """Fail leftover thread-jobs after API restart (Celery rows are kept)."""
    jobs = db.scalars(
        select(Job).where(
            Job.status.in_(JOB_ACTIVE_STATUSES),
            or_(Job.celery_task_id.is_(None), Job.celery_task_id == ""),
        )
    ).all()
    n = 0
    for job in jobs:
        _mark_interrupted(job)
        n += 1
    if n:
        db.commit()
    return n


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

        self._abandon_dead_active()
        active = self.db.scalars(
            select(Job).where(
                Job.school_id == self.school_id,
                Job.status.in_(JOB_ACTIVE_STATUSES),
            )
        ).first()
        if active is not None:
            raise ConflictError(
                f"Уже выполняется задача #{active.id}. "
                "Остановите её или дождитесь завершения."
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

    def _abandon_dead_active(self) -> None:
        jobs = self.db.scalars(
            select(Job).where(
                Job.school_id == self.school_id,
                Job.status.in_(JOB_ACTIVE_STATUSES),
            )
        ).all()
        changed = False
        now = _utc_now()
        for job in jobs:
            if worker_looks_dead(job, now=now):
                _mark_interrupted(job)
                changed = True
        if changed:
            self.db.commit()

    def _finish_cancelled(self, job: Job, payload: dict) -> None:
        job.status = JOB_CANCELLED
        job.result = json.dumps(
            {"type": "cancelled", "count": 0, "message": "Остановлено"},
            ensure_ascii=False,
        )
        job.progress = json.dumps(
            {**payload, "message": "Остановлено"},
            ensure_ascii=False,
        )
        job.error = None
        job.updated_at = _utc_now()

    def cancel(self, job_id: int, *, force: bool = False) -> JobStatusData:
        """Ask a pending/running auto-job to stop. Cooperative: CP-SAT StopSearch.

        force=True (or a second cancel while already cancelling, or a dead worker)
        marks the row cancelled immediately so a new run can start.
        """
        job = require_owned(self.db, Job, job_id, self.school_id)
        if job.status in (JOB_DONE, JOB_FAILED, JOB_CANCELLED):
            raise BadRequestError("Задача уже завершена, останавливать нечего.")

        payload = _parse_json(job.progress) or {}
        celery_id = job.celery_task_id
        immediate = (
            force
            or job.status == JOB_PENDING
            or job.status == JOB_CANCELLING
            or worker_looks_dead(job)
        )
        if immediate:
            self._finish_cancelled(job, payload)
        else:
            job.status = JOB_CANCELLING
            job.progress = json.dumps(
                {**payload, "message": "Остановка…"},
                ensure_ascii=False,
            )
            job.updated_at = _utc_now()
        self.db.commit()
        self.db.refresh(job)
        if celery_id:
            revoke_auto_job(str(celery_id))
        return self.get(job_id)
