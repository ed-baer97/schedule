"""homeroom teacher on school_classes

Revision ID: 10homeroom_teacher
Revises: 9pref_weights
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "10homeroom_teacher"
down_revision = "9pref_weights"
branch_labels = None
depends_on = None


def _column_exists(connection, table: str, column: str) -> bool:
    result = connection.execute(sa.text(f"PRAGMA table_info({table})"))
    return any(row[1] == column for row in result)


def upgrade() -> None:
    conn = op.get_bind()
    if not _column_exists(conn, "school_classes", "homeroom_teacher_id"):
        op.add_column(
            "school_classes",
            sa.Column("homeroom_teacher_id", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("school_classes", "homeroom_teacher_id")
