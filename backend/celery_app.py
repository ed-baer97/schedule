"""Celery application (used when compose profile `queue` is enabled)."""
from __future__ import annotations

from celery import Celery

from app.config import Config

_REDIS_SOCKET_TIMEOUT = 0.4

celery_app = Celery(
    "schedule",
    broker=Config.CELERY_BROKER_URL,
    backend=Config.CELERY_RESULT_BACKEND,
    include=["backend.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_track_started=True,
    # Local Windows has no Redis: fail fast instead of kombu's 20×1s retries.
    broker_connection_retry=False,
    broker_connection_retry_on_startup=False,
    broker_connection_max_retries=0,
    broker_transport_options={
        "socket_connect_timeout": _REDIS_SOCKET_TIMEOUT,
        "socket_timeout": _REDIS_SOCKET_TIMEOUT,
        "max_retries": 0,
        "retry_on_timeout": False,
    },
    result_backend_transport_options={
        "socket_connect_timeout": _REDIS_SOCKET_TIMEOUT,
        "socket_timeout": _REDIS_SOCKET_TIMEOUT,
        "retry_on_timeout": False,
    },
    redis_retry_on_timeout=False,
    redis_socket_connect_timeout=_REDIS_SOCKET_TIMEOUT,
    redis_socket_timeout=_REDIS_SOCKET_TIMEOUT,
)


def broker_is_reachable(url: str | None = None, timeout: float = _REDIS_SOCKET_TIMEOUT) -> bool:
    """True if the Redis broker answers PING within ``timeout`` seconds."""
    raw = (url if url is not None else Config.CELERY_BROKER_URL or "").strip()
    if not raw.startswith(("redis://", "rediss://")):
        return False
    try:
        import redis

        client = redis.Redis.from_url(
            raw,
            socket_connect_timeout=timeout,
            socket_timeout=timeout,
        )
        try:
            return bool(client.ping())
        finally:
            client.close()
    except Exception:
        return False
