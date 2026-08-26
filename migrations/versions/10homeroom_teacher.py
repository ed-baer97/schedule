"""homeroom teacher on school_classes

Revision ID: 10homeroom_teacher
Revises: 9pref_weights
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from migrations.schema_util import column_exists

revision = "10homeroom_teacher"
down_revision = "9pref_weights"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if not column_exists(conn, "school_classes", "homeroom_teacher_id"):
        op.add_column(
            "school_classes",
            sa.Column("homeroom_teacher_id", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("school_classes", "homeroom_teacher_id")
