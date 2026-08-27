"""Cancel / stop auto-schedule jobs."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.models import Job
from backend.deps import SessionLocal
from backend.main import app
from tests.conftest import TEST_SCHOOL_ID, TEST_USER_ID

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clear_jobs() -> None:
    with SessionLocal() as session:
        session.execute(delete(Job))
        session.commit()


def test_cancel_pending_job() -> None:
    from app.services.job_service import JobService

    with SessionLocal() as session:
        queued = JobService(session, TEST_SCHOOL_ID).enqueue_auto(
            kind="repair",
            payload={"school_level": "elementary"},
            created_by_id=TEST_USER_ID,
            dispatch=False,
        )
        job_id = queued["job_id"]

    r = client.post(f"/api/jobs/{job_id}/cancel")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled"

    got = client.get(f"/api/jobs/{job_id}")
    assert got.status_code == 200
    assert got.json()["status"] == "cancelled"


def test_cancel_running_job_sets_cancelling() -> None:
    with SessionLocal() as session:
        job = Job(
            school_id=TEST_SCHOOL_ID,
            kind="auto_all",
            status="running",
            celery_task_id="celery-alive",
        )
        session.add(job)
        session.commit()
        job_id = job.id

    r = client.post(f"/api/jobs/{job_id}/cancel")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelling"


def test_cancel_done_job_rejected() -> None:
    with SessionLocal() as session:
        job = Job(school_id=TEST_SCHOOL_ID, kind="repair", status="done")
        session.add(job)
        session.commit()
        job_id = job.id

    r = client.post(f"/api/jobs/{job_id}/cancel")
    assert r.status_code == 400


def test_enqueue_blocked_while_cancelling() -> None:
    with SessionLocal() as session:
        job = Job(
            school_id=TEST_SCHOOL_ID,
            kind="auto_all",
            status="cancelling",
            celery_task_id="celery-alive",
        )
        session.add(job)
        session.commit()

    queued = client.post(
        "/api/schedule/repair",
        json={"school_level": "elementary"},
    )
    assert queued.status_code == 409


def test_worker_skips_already_cancelled_job() -> None:
    from app.services.job_service import JobService
    from backend.tasks import run_auto_schedule

    with SessionLocal() as session:
        queued = JobService(session, TEST_SCHOOL_ID).enqueue_auto(
            kind="repair",
            payload={"school_level": "elementary"},
            created_by_id=TEST_USER_ID,
            dispatch=False,
        )
        job_id = queued["job_id"]

    cancelled = client.post(f"/api/jobs/{job_id}/cancel")
    assert cancelled.status_code == 200

    out = run_auto_schedule(job_id)
    assert out["status"] == "cancelled"

    got = client.get(f"/api/jobs/{job_id}")
    assert got.json()["status"] == "cancelled"


def test_auto_scheduler_stops_before_work() -> None:
    from app.services.auto_scheduler import AutoScheduler

    with SessionLocal() as session:
        events = list(
            AutoScheduler(
                session, school_id=TEST_SCHOOL_ID, should_stop=lambda: True
            ).repair_iter("elementary")
        )
    assert events
    assert events[-1]["type"] == "cancelled"


def test_enqueue_abandons_dead_in_process_job() -> None:
    """Killed API thread leaves running/cancelling with no worker — allow a new run."""
    with SessionLocal() as session:
        job = Job(school_id=TEST_SCHOOL_ID, kind="auto_all", status="running")
        session.add(job)
        session.commit()
        stuck_id = job.id

    queued = client.post(
        "/api/schedule/repair",
        json={"school_level": "elementary"},
    )
    assert queued.status_code == 202, queued.text
    assert queued.json()["job_id"] != stuck_id

    got = client.get(f"/api/jobs/{stuck_id}")
    assert got.json()["status"] == "failed"
    assert "прерван" in (got.json()["error"] or "")


def test_cancel_dead_running_job_is_immediate() -> None:
    with SessionLocal() as session:
        job = Job(school_id=TEST_SCHOOL_ID, kind="auto_all", status="running")
        session.add(job)
        session.commit()
        job_id = job.id

    r = client.post(f"/api/jobs/{job_id}/cancel")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled"


def test_cancel_cancelling_job_forces_cancelled() -> None:
    with SessionLocal() as session:
        job = Job(
            school_id=TEST_SCHOOL_ID,
            kind="auto_all",
            status="cancelling",
            celery_task_id="celery-alive",
        )
        session.add(job)
        session.commit()
        job_id = job.id

    r = client.post(f"/api/jobs/{job_id}/cancel")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled"


def test_force_cancel_running_celery_job() -> None:
    with SessionLocal() as session:
        job = Job(
            school_id=TEST_SCHOOL_ID,
            kind="auto_all",
            status="running",
            celery_task_id="celery-alive",
        )
        session.add(job)
        session.commit()
        job_id = job.id

    r = client.post(f"/api/jobs/{job_id}/cancel?force=true")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled"


def test_abandon_in_process_jobs_skips_celery() -> None:
    from app.services.job_service import abandon_in_process_jobs

    with SessionLocal() as session:
        thread_job = Job(school_id=TEST_SCHOOL_ID, kind="auto_all", status="running")
        celery_job = Job(
            school_id=TEST_SCHOOL_ID,
            kind="repair",
            status="running",
            celery_task_id="celery-alive",
        )
        session.add_all([thread_job, celery_job])
        session.commit()
        thread_id, celery_id = thread_job.id, celery_job.id

        n = abandon_in_process_jobs(session)
        assert n == 1

    with SessionLocal() as session:
        assert session.get(Job, thread_id).status == "failed"
        assert session.get(Job, celery_id).status == "running"


def test_get_active_empty() -> None:
    r = client.get("/api/jobs/active")
    assert r.status_code == 200, r.text
    assert r.json() == {"job": None}


def test_get_active_running() -> None:
    with SessionLocal() as session:
        job = Job(
            school_id=TEST_SCHOOL_ID,
            kind="auto_all",
            status="running",
            celery_task_id="celery-alive",
        )
        session.add(job)
        session.commit()
        job_id = job.id

    r = client.get("/api/jobs/active")
    assert r.status_code == 200, r.text
    body = r.json()["job"]
    assert body is not None
    assert body["id"] == job_id
    assert body["status"] == "running"
    assert body["kind"] == "auto_all"


def test_get_active_abandons_dead_in_process() -> None:
    with SessionLocal() as session:
        job = Job(school_id=TEST_SCHOOL_ID, kind="auto_all", status="running")
        session.add(job)
        session.commit()
        stuck_id = job.id

    r = client.get("/api/jobs/active")
    assert r.status_code == 200, r.text
    assert r.json() == {"job": None}

    got = client.get(f"/api/jobs/{stuck_id}")
    assert got.json()["status"] == "failed"
    assert "прерван" in (got.json()["error"] or "")


def test_get_active_skips_done() -> None:
    with SessionLocal() as session:
        session.add(Job(school_id=TEST_SCHOOL_ID, kind="repair", status="done"))
        session.commit()

    r = client.get("/api/jobs/active")
    assert r.status_code == 200
    assert r.json() == {"job": None}


def test_enqueue_abandons_stale_celery_job() -> None:
    from datetime import datetime, timedelta, timezone

    old = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=200)
    with SessionLocal() as session:
        job = Job(
            school_id=TEST_SCHOOL_ID,
            kind="auto_all",
            status="running",
            celery_task_id="celery-dead",
            created_at=old,
            updated_at=old,
        )
        session.add(job)
        session.commit()
        stuck_id = job.id

    queued = client.post(
        "/api/schedule/repair",
        json={"school_level": "elementary"},
    )
    assert queued.status_code == 202, queued.text
    got = client.get(f"/api/jobs/{stuck_id}")
    assert got.json()["status"] == "failed"


def test_broker_is_reachable_rejects_non_redis() -> None:
    from backend.celery_app import broker_is_reachable

    assert broker_is_reachable("amqp://localhost") is False
    assert broker_is_reachable("") is False


def test_broker_is_reachable_closed_port() -> None:
    from backend.celery_app import broker_is_reachable

    assert broker_is_reachable("redis://127.0.0.1:1", timeout=0.2) is False


def test_dispatch_fails_closed_when_redis_up_but_enqueue_errors(monkeypatch) -> None:
    from app.services.job_service import JobService
    from backend import tasks

    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(tasks, "broker_is_reachable", lambda: True)

    def _should_not_run(_job_id: int) -> None:
        raise AssertionError("in-process fallback must not run when Redis is up")

    monkeypatch.setattr(tasks, "_start_in_process", _should_not_run)

    def _boom(_job_id: int):
        raise RuntimeError("enqueue failed")

    monkeypatch.setattr(tasks.run_auto_schedule, "delay", _boom)

    with SessionLocal() as session:
        queued = JobService(session, TEST_SCHOOL_ID).enqueue_auto(
            kind="repair",
            payload={"school_level": "elementary"},
            created_by_id=TEST_USER_ID,
            dispatch=False,
        )
        job_id = queued["job_id"]

    tasks._dispatch_auto_job(job_id)

    with SessionLocal() as session:
        job = session.get(Job, job_id)
        assert job is not None
        assert job.status == "failed"
        assert "Celery" in (job.error or "")
