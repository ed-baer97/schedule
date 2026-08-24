"""Map service errors to HTTPException (used by global exception handler)."""
from __future__ import annotations

from fastapi import HTTPException

from app.services.errors import (
    BadRequestError,
    ConflictError,
    NotFoundError,
    ServiceError,
    ValidationConflict,
)


def service_error_to_http(exc: ServiceError) -> HTTPException:
    if isinstance(exc, NotFoundError):
        return HTTPException(status_code=404, detail=exc.message)
    if isinstance(exc, ValidationConflict):
        return HTTPException(status_code=422, detail={"errors": exc.errors})
    if isinstance(exc, BadRequestError):
        return HTTPException(status_code=400, detail=exc.message)
    if isinstance(exc, ConflictError):
        return HTTPException(status_code=409, detail=exc.message)
    return HTTPException(status_code=500, detail=str(exc))


def raise_http(exc: Exception) -> None:
    """Legacy helper; prefer the global ServiceError handler in main.py."""
    if isinstance(exc, ServiceError):
        raise service_error_to_http(exc) from exc
    raise exc
