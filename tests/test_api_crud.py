"""CRUD smoke tests for directories already on FastAPI get_db."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.models import Classroom, SchoolClass, Shift, Teacher
from backend.deps import SessionLocal
from backend.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clear() -> None:
    with SessionLocal() as session:
        session.execute(delete(SchoolClass))
        session.execute(delete(Teacher))
        session.execute(delete(Classroom))
        session.execute(delete(Shift))
        session.commit()


def test_classroom_crud() -> None:
    created = client.post(
        "/api/classrooms/",
        json={"number": "101", "name": "Математика", "classes_capacity": 1},
    )
    assert created.status_code == 200, created.text
    cid = created.json()["id"]
    assert created.json()["display_name"]

    listed = client.get("/api/classrooms/")
    assert listed.status_code == 200
    assert any(r["id"] == cid for r in listed.json())

    updated = client.put(
        f"/api/classrooms/{cid}",
        json={"number": "101", "name": "Алгебра", "classes_capacity": 2},
    )
    assert updated.status_code == 200
    assert updated.json()["classes_capacity"] == 2

    deleted = client.delete(f"/api/classrooms/{cid}")
    assert deleted.status_code == 204
    assert client.get(f"/api/classrooms/{cid}").status_code == 404


def test_shift_and_class_crud() -> None:
    shift = client.post(
        "/api/shifts/",
        json={
            "name": "1 смена",
            "school_level": "elementary",
            "start_lesson": 1,
            "lessons_count": 5,
            "working_days": 5,
            "max_lessons_per_day": 5,
        },
    )
    assert shift.status_code == 200, shift.text
    shift_id = shift.json()["id"]

    cls = client.post(
        "/api/school-classes/",
        json={
            "name": "1А",
            "school_level": "elementary",
            "shift_id": shift_id,
        },
    )
    assert cls.status_code == 200, cls.text
    class_id = cls.json()["id"]
    assert cls.json()["shift"]["name"] == "1 смена"

    batch = client.post(
        "/api/school-classes/batch-shift",
        json={"class_ids": [class_id], "shift_id": None},
    )
    assert batch.status_code == 200, batch.text
    updated = next(c for c in batch.json() if c["id"] == class_id)
    assert updated["shift_id"] is None

    assert client.delete(f"/api/school-classes/{class_id}").status_code == 204
    assert client.delete(f"/api/shifts/{shift_id}").status_code == 204


def test_teacher_crud_roundtrip() -> None:
    created = client.post(
        "/api/teachers/",
        json={"full_name": "Петров П.П.", "email": "p@example.com"},
    )
    assert created.status_code == 200, created.text
    tid = created.json()["id"]

    updated = client.put(
        f"/api/teachers/{tid}",
        json={"full_name": "Петров Пётр", "email": None, "phone": "123"},
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["full_name"] == "Петров Пётр"
    assert body["phone"] == "123"

    assert client.delete(f"/api/teachers/{tid}").status_code == 204
