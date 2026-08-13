"""Database bootstrap for FastAPI startup (same DB as Flask)."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)

_CORE_TABLES = frozenset(
    {
        "teachers",
        "classrooms",
        "school_classes",
        "shifts",
        "subjects",
        "teaching_assignments",
    }
)

# Columns required by current SQLAlchemy models (SQLite schema drift guard)
_REQUIRED_COLUMNS: dict[str, frozenset[str]] = {
    "classrooms": frozenset({"classes_capacity"}),
    "shifts": frozenset(
        {"working_days", "max_lessons_per_day", "class_hour_day", "class_hour_start", "class_hour_end"}
    ),
    "schedule_settings": frozenset({"classroom_mode", "elementary_group_subjects_leave"}),
    "teachers": frozenset({"home_classroom_id"}),
}


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


def ensure_database(flask_app) -> dict[str, Any]:
    """Apply pending Alembic migrations; create tables in empty dev DB."""
    from app import db

    with flask_app.app_context():
        before = check_schema(db.engine)
        if before["schema_ready"]:
            return {**before, "migrated": False, "message": "ok"}

        if before["tables_count"] == 0:
            try:
                from flask_migrate import upgrade

                upgrade()
                logger.info("Database: flask db upgrade (empty database)")
            except Exception as exc:
                logger.warning("Migration failed (%s), using create_all()", exc)
                db.create_all()
        else:
            try:
                from flask_migrate import upgrade

                upgrade()
                logger.info("Database: flask db upgrade (pending revisions)")
            except Exception as exc:
                logger.warning("Could not run upgrade: %s", exc)
                if not before["schema_ready"]:
                    db.create_all()

        after = check_schema(db.engine)
        after["migrated"] = True
        if not after["schema_ready"]:
            after["message"] = (
                "Схема неполная. Из корня проекта: set FLASK_APP=run.py && flask db upgrade"
            )
        else:
            after["message"] = "ok"
        return after
