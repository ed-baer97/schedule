"""Dialect-agnostic helpers for Alembic revisions (SQLite and Postgres)."""
from sqlalchemy import inspect


def table_exists(connection, table: str) -> bool:
    return table in inspect(connection).get_table_names()


def column_exists(connection, table: str, column: str) -> bool:
    insp = inspect(connection)
    if table not in insp.get_table_names():
        return False
    return any(col["name"] == column for col in insp.get_columns(table))
