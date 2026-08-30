"""In-process cancel flags for auto-schedule jobs.

SQLite often holds a read snapshot on the solver session for the whole CP-SAT
search. A cooperative cancel that only writes ``jobs.status`` then waits on that
lock, so StopSearch never runs. The Event lives in this API process and is
checked by ``should_stop`` without touching the database.

Celery workers are another process: they still need the DB/WAL path.
"""
from __future__ import annotations

import threading

_lock = threading.Lock()
_events: dict[int, threading.Event] = {}


def request_cancel(job_id: int) -> None:
    with _lock:
        ev = _events.get(job_id)
        if ev is None:
            ev = threading.Event()
            _events[job_id] = ev
        ev.set()


def is_cancel_requested(job_id: int) -> bool:
    with _lock:
        ev = _events.get(job_id)
        return bool(ev is not None and ev.is_set())


def clear_cancel(job_id: int) -> None:
    with _lock:
        _events.pop(job_id, None)
