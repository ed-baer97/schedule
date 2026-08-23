"""Map service errors to HTTPException."""
from __future__ import annotations

from fastapi import HTTPException

from app.services.errors import (
    BadRequestError,
    ConflictError,
    NotFoundError,
    ValidationConflict,
)


def raise_http(exc: Exception) -> None:
    if isinstance(exc, NotFoundError):
        raise HTTPException(status_code=404, detail=exc.message) from exc
    if isinstance(exc, ValidationConflict):
        raise HTTPException(status_code=422, detail={"errors": exc.errors}) from exc
    if isinstance(exc, BadRequestError):
        raise HTTPException(status_code=400, detail=exc.message) from exc
    if isinstance(exc, ConflictError):
        raise HTTPException(status_code=409, detail=exc.message) from exc
    raise exc
