"""Celery tasks for background auto-scheduling."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from app.config import Config
from app.models.job import JOB_DONE, JOB_FAILED, JOB_RUNNING
from app.services.auto_scheduler import AutoScheduler
from app.services.job_dispatch import set_dispatcher
from backend.celery_app import celery_app
from backend.deps import SessionLocal


def _utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _update_job(db, job_id: int, **fields) -> None:
    from app.models import Job

    job = db.get(Job, job_id)
    if job is None:
        return
    for k, v in fields.items():
        setattr(job, k, v)
    job.updated_at = _utc_now()
    db.commit()


def _dispatch_auto_job(job_id: int) -> None:
    """Celery delay with sync fallback when broker is unavailable."""
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
        run_auto_schedule(job_id)


@celery_app.task(bind=True, name="schedule.run_auto")
def run_auto_schedule(self, job_id: int) -> dict:
    db = SessionLocal()
    try:
        from app.models import Job

        job = db.get(Job, job_id)
        if job is None:
            return {"error": "job not found"}

        payload = json.loads(job.progress or "{}")
        kind = job.kind
        school_id = job.school_id
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

        scheduler = AutoScheduler(db, school_id=school_id)
        last_event: dict = {}
        limit = int(payload.get("time_limit_sec") or Config.SOLVER_TIME_LIMIT_SEC)

        if kind == "auto_all":
            iterator = scheduler.auto_schedule_all_iter(
                payload.get("school_level", "elementary"),
                solver=payload.get("solver", True),
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
            if event.get("type") == "progress":
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
            _update_job(db, job_id, status=JOB_FAILED, error=str(exc))
        except Exception:
            pass
        raise
    finally:
        db.close()


set_dispatcher(_dispatch_auto_job)
