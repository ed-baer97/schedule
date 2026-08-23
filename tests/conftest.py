"""
Pytest configuration: isolated SQLite DB for API tests.

DATABASE_URL must be set before any import of app.config.
"""
from __future__ import annotations

import os
import tempfile

_fd, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["DATABASE_URL"] = "sqlite:///" + _TEST_DB_PATH.replace("\\", "/")
os.environ["SECRET_KEY"] = "test-secret"
os.environ["COOKIE_SECURE"] = "false"
os.environ["BOOTSTRAP_ADMIN_EMAIL"] = ""
os.environ["BOOTSTRAP_ADMIN_PASSWORD"] = ""

import pytest  # noqa: E402
from sqlalchemy import select  # noqa: E402

import app.models  # noqa: E402, F401
from app.db import Base  # noqa: E402
from app.models import ScheduleSettings, School, User  # noqa: E402
from app.models.user import ROLE_SCHOOL_ADMIN  # noqa: E402
from backend.deps import SessionLocal, engine, get_current_user  # noqa: E402
from backend.main import app  # noqa: E402
from backend.security import hash_password  # noqa: E402

Base.metadata.create_all(bind=engine)

with SessionLocal() as _session:
    school = _session.scalars(select(School)).first()
    if school is None:
        school = School(name="Test School", slug="test", is_active=True)
        _session.add(school)
        _session.flush()
        for level in ("elementary", "secondary"):
            _session.add(
                ScheduleSettings(
                    school_id=school.id,
                    school_level=level,
                    max_lessons_per_subject_per_day=2,
                    classroom_mode="class_room",
                    elementary_group_subjects_leave=True,
                )
            )
    user = _session.scalars(
        select(User).where(User.email == "test@example.com")
    ).first()
    if user is None:
        user = User(
            email="test@example.com",
            password_hash=hash_password("testpass123"),
            role=ROLE_SCHOOL_ADMIN,
            school_id=school.id,
            is_active=True,
        )
        _session.add(user)
    _session.commit()
    TEST_SCHOOL_ID = int(school.id)
    TEST_USER_ID = int(user.id)


def _override_user_attached() -> User:
    """Return a detached User with school_id for school-scoped routes."""
    db = SessionLocal()
    user = db.get(User, TEST_USER_ID)
    assert user is not None
    db.expunge(user)
    db.close()
    return user


app.dependency_overrides[get_current_user] = _override_user_attached


@pytest.fixture
def school_id() -> int:
    return TEST_SCHOOL_ID


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    app.dependency_overrides.clear()
    try:
        os.unlink(_TEST_DB_PATH)
    except OSError:
        pass
