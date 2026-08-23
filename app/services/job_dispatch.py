"""Port for dispatching auto-schedule jobs (Celery wired in backend)."""
from __future__ import annotations

from typing import Callable

_Dispatcher = Callable[[int], None]

_dispatcher: _Dispatcher | None = None


def set_dispatcher(fn: _Dispatcher | None) -> None:
    global _dispatcher
    _dispatcher = fn


def dispatch_auto_job(job_id: int) -> None:
    """Run registered dispatcher, or no-op if none (tests / early boot)."""
    if _dispatcher is not None:
        _dispatcher(job_id)
