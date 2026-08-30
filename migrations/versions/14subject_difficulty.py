"""subjects.difficulty: easy, medium, hard

Revision ID: 14subject_difficulty
Revises: 13classroom_school_level
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from migrations.schema_util import column_exists

revision = "14subject_difficulty"
down_revision = "13classroom_school_level"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if not column_exists(conn, "subjects", "difficulty"):
        op.add_column(
            "subjects",
            sa.Column(
                "difficulty",
                sa.String(length=20),
                nullable=False,
                server_default="medium",
            ),
        )


def downgrade() -> None:
    conn = op.get_bind()
    if column_exists(conn, "subjects", "difficulty"):
        op.drop_column("subjects", "difficulty")
