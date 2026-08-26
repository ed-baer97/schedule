"""Portable Alembic column_exists (SQLite and Postgres)."""
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine

from migrations.schema_util import column_exists, table_exists


def test_column_exists_sqlite() -> None:
    engine = create_engine("sqlite:///:memory:")
    meta = MetaData()
    Table("classrooms", meta, Column("id", Integer, primary_key=True), Column("number", String(20)))
    meta.create_all(engine)
    with engine.connect() as conn:
        assert column_exists(conn, "classrooms", "number") is True
        assert column_exists(conn, "classrooms", "is_exclusive") is False
        assert column_exists(conn, "missing_table", "id") is False
        assert table_exists(conn, "classrooms") is True
        assert table_exists(conn, "nope") is False
