"""Preference weights on schedule_settings.

Revision ID: 9pref_weights
Revises: 8auth_tenancy
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "9pref_weights"
down_revision = "8auth_tenancy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "schedule_settings",
        sa.Column("pref_teacher_gaps", sa.Integer(), nullable=False, server_default="5"),
    )
    op.add_column(
        "schedule_settings",
        sa.Column("pref_hard_subjects_early", sa.Integer(), nullable=False, server_default="5"),
    )
    op.add_column(
        "schedule_settings",
        sa.Column("pref_adjacent_pairs", sa.Integer(), nullable=False, server_default="5"),
    )
    op.add_column(
        "schedule_settings",
        sa.Column("pref_classroom_stability", sa.Integer(), nullable=False, server_default="5"),
    )


def downgrade() -> None:
    op.drop_column("schedule_settings", "pref_classroom_stability")
    op.drop_column("schedule_settings", "pref_adjacent_pairs")
    op.drop_column("schedule_settings", "pref_hard_subjects_early")
    op.drop_column("schedule_settings", "pref_teacher_gaps")
