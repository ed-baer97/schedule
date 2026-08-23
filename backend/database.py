"""Database bootstrap for FastAPI startup."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import inspect, text

from app.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

_CORE_TABLES = frozenset(
    {
        "schools",
        "users",
        "teachers",
        "classrooms",
        "school_classes",
        "shifts",
        "subjects",
        "teaching_assignments",
    }
)

_REQUIRED_COLUMNS: dict[str, frozenset[str]] = {
    "classrooms": frozenset({"classes_capacity"}),
    "shifts": frozenset(
        {"working_days", "max_lessons_per_day", "class_hour_day", "class_hour_start", "class_hour_end"}
    ),
    "schedule_settings": frozenset({"classroom_mode", "elementary_group_subjects_leave"}),
    "teachers": frozenset({"home_classroom_id"}),
}

_SCHEMA_HINT = "Схема неполная. Из корня проекта: alembic upgrade head"


def _missing_columns(engine) -> dict[str, list[str]]:
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    out: dict[str, list[str]] = {}
    for table, required in _REQUIRED_COLUMNS.items():
        if table not in tables:
            continue
        present = {c["name"] for c in insp.get_columns(table)}
        missing = sorted(required - present)
        if missing:
            out[table] = missing
    return out


def check_schema(engine) -> dict[str, Any]:
    """Inspect DB without mutating it."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        insp = inspect(engine)
        tables = set(insp.get_table_names())
        missing_tables = sorted(_CORE_TABLES - tables)
        missing_columns = _missing_columns(engine)
        schema_ready = len(missing_tables) == 0 and len(missing_columns) == 0
        return {
            "connected": True,
            "tables_count": len(tables),
            "schema_ready": schema_ready,
            "missing_tables": missing_tables,
            "missing_columns": missing_columns,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "connected": False,
            "tables_count": 0,
            "schema_ready": False,
            "missing_tables": sorted(_CORE_TABLES),
            "missing_columns": {},
            "error": str(exc),
        }


def _run_alembic_upgrade() -> None:
    from alembic import command
    from alembic.config import Config as AlembicConfig

    cfg = AlembicConfig(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    command.upgrade(cfg, "head")


def ensure_database(engine) -> dict[str, Any]:
    """Apply pending Alembic migrations; create tables in empty dev DB."""
    from app.db import Base
    import app.models  # noqa: F401

    before = check_schema(engine)
    if before["schema_ready"]:
        return {**before, "migrated": False, "message": "ok"}

    if before["tables_count"] == 0:
        try:
            _run_alembic_upgrade()
            logger.info("Database: alembic upgrade head (empty database)")
        except Exception as exc:
            logger.warning("Migration failed (%s), using create_all()", exc)
            Base.metadata.create_all(bind=engine)
    else:
        try:
            _run_alembic_upgrade()
            logger.info("Database: alembic upgrade head (pending revisions)")
        except Exception as exc:
            logger.warning("Could not run upgrade: %s", exc)
            if not before["schema_ready"]:
                Base.metadata.create_all(bind=engine)

    after = check_schema(engine)
    after["migrated"] = True
    if not after["schema_ready"]:
        after["message"] = _SCHEMA_HINT
    else:
        after["message"] = "ok"
    return after
