"""Health check."""
from fastapi import APIRouter

from backend.celery_app import broker_is_reachable
from backend.database import check_schema
from backend.deps import engine

router = APIRouter()


@router.get("/health")
def health() -> dict:
    db = check_schema(engine)
    status = "ok" if db.get("connected") and db.get("schema_ready") else "degraded"
    if not db.get("connected"):
        status = "error"
    return {
        "status": status,
        "database": db,
        "queue": {"broker_reachable": broker_is_reachable()},
    }
