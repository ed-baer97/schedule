"""School-scoped entity lookup for services."""
from __future__ import annotations

from typing import TypeVar

from sqlalchemy.orm import Session

from app.services.errors import NotFoundError

T = TypeVar("T")


def require_owned(db: Session, model: type[T], obj_id: int, school_id: int) -> T:
    obj = db.get(model, obj_id)
    if obj is None or getattr(obj, "school_id", None) != school_id:
        raise NotFoundError("Not found")
    return obj
