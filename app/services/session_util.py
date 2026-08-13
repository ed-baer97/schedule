"""Resolve a SQLAlchemy Session for services (FastAPI SessionLocal or Flask db.session)."""
from __future__ import annotations

from sqlalchemy.orm import Session


def resolve_session(session: Session | None = None) -> Session:
    if session is not None:
        return session
    from app import db

    return db.session
