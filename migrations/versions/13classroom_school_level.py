"""classrooms.school_level: NULL=shared, elementary, secondary

Revision ID: 13classroom_school_level
Revises: 12classroom_subjects
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from migrations.schema_util import column_exists

revision = "13classroom_school_level"
down_revision = "12classroom_subjects"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if not column_exists(conn, "classrooms", "school_level"):
        op.add_column(
            "classrooms",
            sa.Column("school_level", sa.String(length=20), nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()
    if column_exists(conn, "classrooms", "school_level"):
        op.drop_column("classrooms", "school_level")
