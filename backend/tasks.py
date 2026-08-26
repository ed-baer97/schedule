"""Celery tasks for background auto-scheduling."""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone

from app.config import Config
from app.models.job import (
    JOB_CANCELLED,
    JOB_CANCELLING,
    JOB_DONE,
    JOB_FAILED,
    JOB_PENDING,
    JOB_RUNNING,
    JOB_TERMINAL_STATUSES,
)
from app.services.auto_scheduler import AutoScheduler
from app.services.job_dispatch import set_dispatcher, set_revoker
from backend.celery_app import celery_app
from backend.deps import SessionLocal


def _utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


_PROGRESS_THROTTLE_SEC = 0.5
_last_progress_commit: dict[int, float] = {}


def _update_job(db, job_id: int, **fields) -> None:
    from app.models import Job

    job = db.get(Job, job_id)
    if job is None:
        return
    new_status = fields.get("status")
    if job.status in JOB_TERMINAL_STATUSES:
        return
    if job.status == JOB_CANCELLING and new_status in (
        JOB_RUNNING,
        JOB_DONE,
        JOB_PENDING,
        JOB_FAILED,
    ):
        return
    progress_only = new_status is None and set(fields) <= {"progress"}
    now = time.monotonic()
    if progress_only:
        last = _last_progress_commit.get(job_id, 0.0)
        if now - last < _PROGRESS_THROTTLE_SEC:
            return
        _last_progress_commit[job_id] = now
    else:
        _last_progress_commit.pop(job_id, None)
    for k, v in fields.items():
        setattr(job, k, v)
    job.updated_at = _utc_now()
    db.commit()


def _job_wants_cancel(db, job_id: int) -> bool:
    from app.models import Job

    job = db.get(Job, job_id)
    if job is None:
        return False
    db.refresh(job)
    return job.status in (JOB_CANCELLING, JOB_CANCELLED)


def _make_should_stop(job_id: int):
    last = {"t": 0.0, "v": False}

    def should_stop() -> bool:
        now = time.monotonic()
        if now - last["t"] < 0.3:
            return bool(last["v"])
        db = SessionLocal()
        try:
            from app.models import Job

            job = db.get(Job, job_id)
            last["v"] = job is not None and job.status in (JOB_CANCELLING, JOB_CANCELLED)
            last["t"] = now
            if job is not None and job.status not in JOB_TERMINAL_STATUSES:
                job.updated_at = _utc_now()
                try:
                    db.commit()
                except Exception:
                    db.rollback()
            return bool(last["v"])
        except Exception:
            return False
        finally:
            db.close()

    return should_stop


def _finish_cancelled(db, job_id: int, payload: dict, last_event: dict | None = None) -> None:
    event = last_event or {}
    _update_job(
        db,
        job_id,
        status=JOB_CANCELLED,
        result=json.dumps(
            {
                "type": "cancelled",
                "count": event.get("count", 0),
                "message": event.get("message") or "Остановлено",
            },
            ensure_ascii=False,
        ),
        progress=json.dumps(
            {
                **payload,
                "current": event.get("current", payload.get("current", 0)),
                "total": event.get("total", payload.get("total", 0)),
                "message": "Остановлено",
            },
            ensure_ascii=False,
        ),
        error=None,
    )


def _revoke_celery_task(task_id: str) -> None:
    try:
        celery_app.control.revoke(task_id, terminate=False)
    except Exception:
        pass


def _run_auto_schedule_sync(job_id: int) -> None:
    try:
        run_auto_schedule(job_id)
    except Exception:
        pass


def _dispatch_auto_job(job_id: int) -> None:
    """Celery delay with thread fallback when broker is unavailable.

    Tests keep the previous in-process sync call so SQLite stays single-threaded
    and the suite never waits on a Redis broker.
    """
    if os.environ.get("PYTEST_CURRENT_TEST"):
        run_auto_schedule(job_id)
        return
    try:
        async_result = run_auto_schedule.delay(job_id)
        db = SessionLocal()
        try:
            from app.models import Job

            job = db.get(Job, job_id)
            if job is not None:
                job.celery_task_id = async_result.id
                db.commit()
        finally:
            db.close()
    except Exception:
        threading.Thread(
            target=_run_auto_schedule_sync,
            args=(job_id,),
            daemon=True,
            name=f"auto-job-{job_id}",
        ).start()


@celery_app.task(bind=True, name="schedule.run_auto")
def run_auto_schedule(self, job_id: int) -> dict:
    db = SessionLocal()
    try:
        from app.models import Job

        job = db.get(Job, job_id)
        if job is None:
            return {"error": "job not found"}

        payload = json.loads(job.progress or "{}")
        if not isinstance(payload, dict):
            payload = {}
        kind = job.kind
        school_id = job.school_id

        if job.status in (JOB_CANCELLED, JOB_CANCELLING):
            _finish_cancelled(db, job_id, payload)
            return {"status": "cancelled", "job_id": job_id}

        _update_job(
            db,
            job_id,
            status=JOB_RUNNING,
            celery_task_id=self.request.id,
            progress=json.dumps(
                {**payload, "current": 0, "total": 0, "message": "Запуск…"},
                ensure_ascii=False,
            ),
        )

        scheduler = AutoScheduler(
            db, school_id=school_id, should_stop=_make_should_stop(job_id)
        )
        last_event: dict = {}
        last_progress_t = 0.0
        wrote_progress = False
        limit = int(payload.get("time_limit_sec") or Config.SOLVER_TIME_LIMIT_SEC)

        if kind == "auto_all":
            iterator = scheduler.auto_schedule_all_iter(
                payload.get("school_level", "elementary"),
                shift_id=payload.get("shift_id"),
                time_limit_sec=limit,
                random_seed=payload.get("random_seed"),
            )
        elif kind == "auto_by_teacher":
            iterator = scheduler.schedule_by_teacher_ladder_iter(
                int(payload["teacher_id"]),
                payload.get("school_level", "elementary"),
            )
        elif kind == "repair":
            iterator = scheduler.repair_iter(
                payload.get("school_level", "elementary"),
                teacher_id=payload.get("teacher_id"),
                class_id=payload.get("class_id"),
            )
        else:
            _update_job(db, job_id, status=JOB_FAILED, error=f"Unknown kind {kind}")
            return {"error": "unknown kind"}

        for event in iterator:
            last_event = event
            now = time.monotonic()
            check_cancel = (not wrote_progress) or now - last_progress_t >= 0.5
            if event.get("type") == "cancelled" or (
                check_cancel and _job_wants_cancel(db, job_id)
            ):
                _finish_cancelled(db, job_id, payload, event)
                return {"status": "cancelled", "job_id": job_id}
            if event.get("type") == "progress" and check_cancel:
                wrote_progress = True
                last_progress_t = now
                _update_job(
                    db,
                    job_id,
                    progress=json.dumps(
                        {
                            **payload,
                            "current": event.get("current", 0),
                            "total": event.get("total", 0),
                            "message": event.get("message") or "",
                        },
                        ensure_ascii=False,
                    ),
                )

        if _job_wants_cancel(db, job_id):
            _finish_cancelled(db, job_id, payload, last_event)
            return {"status": "cancelled", "job_id": job_id}

        if not payload.get("diagnose"):
            last_event.pop("diagnostics", None)

        _update_job(
            db,
            job_id,
            status=JOB_DONE,
            result=json.dumps(last_event, ensure_ascii=False),
            progress=json.dumps(
                {
                    **payload,
                    "current": last_event.get("count", payload.get("current", 0)),
                    "total": last_event.get("count", payload.get("total", 0)),
                    "message": "Готово",
                },
                ensure_ascii=False,
            ),
        )
        return {"status": "done", "job_id": job_id}
    except Exception as exc:  # noqa: BLE001
        try:
            if _job_wants_cancel(db, job_id):
                _finish_cancelled(db, job_id, {})
            else:
                _update_job(db, job_id, status=JOB_FAILED, error=str(exc))
        except Exception:
            pass
        raise
    finally:
        db.close()


set_dispatcher(_dispatch_auto_job)
set_revoker(_revoke_celery_task)
