"""Schedule variants: main / temporary / monthly weeks; hours as float.

Revision ID: 19schedule_variants
Revises: 18subject_group
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from migrations.schema_util import column_exists

revision = "19schedule_variants"
down_revision = "18subject_group"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if not column_exists(conn, "schedule_cells", "schedule_kind"):
        with op.batch_alter_table("schedule_cells") as batch:
            batch.add_column(
                sa.Column(
                    "schedule_kind",
                    sa.String(length=20),
                    nullable=False,
                    server_default="main",
                )
            )
            batch.add_column(
                sa.Column(
                    "week_index",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                )
            )
            batch.drop_constraint("uq_schedule_cell", type_="unique")
            batch.create_unique_constraint(
                "uq_schedule_cell",
                [
                    "class_id",
                    "day_of_week",
                    "lesson_number",
                    "assignment_id",
                    "schedule_kind",
                    "week_index",
                ],
            )
    if column_exists(conn, "teaching_assignments", "hours_per_week"):
        with op.batch_alter_table("teaching_assignments") as batch:
            batch.alter_column(
                "hours_per_week",
                existing_type=sa.Integer(),
                type_=sa.Float(),
                existing_nullable=False,
            )


def downgrade() -> None:
    conn = op.get_bind()
    if column_exists(conn, "schedule_cells", "schedule_kind"):
        with op.batch_alter_table("schedule_cells") as batch:
            batch.drop_constraint("uq_schedule_cell", type_="unique")
            batch.create_unique_constraint(
                "uq_schedule_cell",
                ["class_id", "day_of_week", "lesson_number", "assignment_id"],
            )
            batch.drop_column("week_index")
            batch.drop_column("schedule_kind")
    if column_exists(conn, "teaching_assignments", "hours_per_week"):
        with op.batch_alter_table("teaching_assignments") as batch:
            batch.alter_column(
                "hours_per_week",
                existing_type=sa.Float(),
                type_=sa.Integer(),
                existing_nullable=False,
            )
