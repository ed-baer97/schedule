"""classrooms.subgroup_only; drop subjects.requires_subgroup

Revision ID: 17classroom_subgroup_only
Revises: 16requires_subgroup
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from migrations.schema_util import column_exists

revision = "17classroom_subgroup_only"
down_revision = "16requires_subgroup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if not column_exists(conn, "classrooms", "subgroup_only"):
        op.add_column(
            "classrooms",
            sa.Column(
                "subgroup_only",
                sa.Boolean(),
                nullable=False,
                server_default="0",
            ),
        )
    if column_exists(conn, "subjects", "requires_subgroup"):
        op.drop_column("subjects", "requires_subgroup")


def downgrade() -> None:
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
    if column_exists(conn, "classrooms", "subgroup_only"):
        op.drop_column("classrooms", "subgroup_only")
