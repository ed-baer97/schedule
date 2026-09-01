"""subjects.requires_subgroup: subject is always a subgroup lesson

Revision ID: 16requires_subgroup
Revises: 15class_hour_lessons
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from migrations.schema_util import column_exists

revision = "16requires_subgroup"
down_revision = "15class_hour_lessons"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if not column_exists(conn, "subjects", "requires_subgroup"):
        op.add_column(
            "subjects",
            sa.Column(
                "requires_subgroup",
                sa.Boolean(),
                nullable=False,
                server_default="0",
            ),
        )


def downgrade() -> None:
    conn = op.get_bind()
    if column_exists(conn, "subjects", "requires_subgroup"):
        op.drop_column("subjects", "requires_subgroup")
