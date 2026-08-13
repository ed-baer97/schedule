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

import app.models  # noqa: E402, F401 — register all models on metadata
from app.db import Base  # noqa: E402
from backend.deps import engine  # noqa: E402

Base.metadata.create_all(bind=engine)


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    try:
        os.unlink(_TEST_DB_PATH)
    except OSError:
        pass
