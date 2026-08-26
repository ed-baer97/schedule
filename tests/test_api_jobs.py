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
        job = Job(school_id=TEST_SCHOOL_ID, kind="auto_all", status="running")
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
        job = Job(school_id=TEST_SCHOOL_ID, kind="auto_all", status="cancelling")
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
