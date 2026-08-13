"""FastAPI smoke tests."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.models import Teacher
from backend.deps import SessionLocal
from backend.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clear_teachers() -> None:
    with SessionLocal() as session:
        session.execute(delete(Teacher))
        session.commit()


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("ok", "degraded")
    assert body["database"]["connected"] is True
    assert body["database"]["schema_ready"] is True


def test_dashboard_stats() -> None:
    response = client.get("/api/dashboard/stats")
    assert response.status_code == 200
    data = response.json()
    assert "teachers_count" in data
    assert "classes_count" in data


def test_teachers_empty() -> None:
    response = client.get("/api/teachers/")
    assert response.status_code == 200
    assert response.json() == []


def test_teacher_not_found() -> None:
    response = client.get("/api/teachers/99999")
    assert response.status_code == 404


def test_teachers_list_one() -> None:
    with SessionLocal() as session:
        session.add(Teacher(full_name="Тестовый учитель", email="t@example.com"))
        session.commit()

    response = client.get("/api/teachers/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["full_name"] == "Тестовый учитель"
    assert data[0]["email"] == "t@example.com"

    tid = data[0]["id"]
    one = client.get(f"/api/teachers/{tid}")
    assert one.status_code == 200
    assert one.json()["full_name"] == "Тестовый учитель"
