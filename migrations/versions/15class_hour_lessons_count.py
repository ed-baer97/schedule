"""shifts.class_hour_lessons_count: fewer lessons on the class-hour day

Revision ID: 15class_hour_lessons
Revises: 14subject_difficulty
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from migrations.schema_util import column_exists

revision = "15class_hour_lessons"
down_revision = "14subject_difficulty"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if not column_exists(conn, "shifts", "class_hour_lessons_count"):
        op.add_column(
            "shifts",
            sa.Column("class_hour_lessons_count", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()
    if column_exists(conn, "shifts", "class_hour_lessons_count"):
        op.drop_column("shifts", "class_hour_lessons_count")
