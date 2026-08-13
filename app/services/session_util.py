"""Resolve a SQLAlchemy Session for domain services."""
from __future__ import annotations

from sqlalchemy.orm import Session


def resolve_session(session: Session | None = None) -> Session:
    if session is None:
        raise RuntimeError("SQLAlchemy Session is required")
    return session
