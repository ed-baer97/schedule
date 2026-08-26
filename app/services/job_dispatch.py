"""Port for dispatching auto-schedule jobs (Celery wired in backend)."""
from __future__ import annotations

from typing import Callable

_Dispatcher = Callable[[int], None]
_Revoker = Callable[[str], None]

_dispatcher: _Dispatcher | None = None
_revoker: _Revoker | None = None


def set_dispatcher(fn: _Dispatcher | None) -> None:
    global _dispatcher
    _dispatcher = fn


def set_revoker(fn: _Revoker | None) -> None:
    global _revoker
    _revoker = fn


def dispatch_auto_job(job_id: int) -> None:
    """Run registered dispatcher, or no-op if none (tests / early boot)."""
    if _dispatcher is not None:
        _dispatcher(job_id)


def revoke_auto_job(celery_task_id: str) -> None:
    """Best-effort revoke of a queued Celery task (no-op if unset)."""
    if _revoker is not None and celery_task_id:
        _revoker(celery_task_id)
