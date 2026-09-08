"""subjects.subject_group replaces difficulty; pref_same_group_adjacent

Revision ID: 18subject_group
Revises: 17classroom_subgroup_only
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from migrations.schema_util import column_exists

revision = "18subject_group"
down_revision = "17classroom_subgroup_only"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if not column_exists(conn, "subjects", "subject_group"):
        op.add_column(
            "subjects",
            sa.Column(
                "subject_group",
                sa.String(length=20),
                nullable=False,
                server_default="humanities",
            ),
        )
        if column_exists(conn, "subjects", "difficulty"):
            conn.execute(
                sa.text(
                    """
                    UPDATE subjects SET subject_group = CASE difficulty
                        WHEN 'easy' THEN 'practical'
                        WHEN 'hard' THEN 'natural_math'
                        ELSE 'humanities'
                    END
                    """
                )
            )
        rows = conn.execute(sa.text("SELECT id, name FROM subjects")).fetchall()
        for sid, name in rows:
            guessed = _guess(name)
            if guessed:
                conn.execute(
                    sa.text(
                        "UPDATE subjects SET subject_group = :g WHERE id = :id"
                    ),
                    {"g": guessed, "id": sid},
                )
    if column_exists(conn, "subjects", "difficulty"):
        with op.batch_alter_table("subjects") as batch:
            batch.drop_column("difficulty")

    if not column_exists(conn, "schedule_settings", "pref_same_group_adjacent"):
        op.add_column(
            "schedule_settings",
            sa.Column(
                "pref_same_group_adjacent",
                sa.Integer(),
                nullable=False,
                server_default="5",
            ),
        )
        if column_exists(conn, "schedule_settings", "pref_hard_subjects_early"):
            conn.execute(
                sa.text(
                    "UPDATE schedule_settings SET pref_same_group_adjacent = "
                    "COALESCE(pref_hard_subjects_early, 5)"
                )
            )


def downgrade() -> None:
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
        if column_exists(conn, "subjects", "subject_group"):
            conn.execute(
                sa.text(
                    """
                    UPDATE subjects SET difficulty = CASE subject_group
                        WHEN 'practical' THEN 'easy'
                        WHEN 'natural_math' THEN 'hard'
                        ELSE 'medium'
                    END
                    """
                )
            )
    if column_exists(conn, "subjects", "subject_group"):
        with op.batch_alter_table("subjects") as batch:
            batch.drop_column("subject_group")
    if column_exists(conn, "schedule_settings", "pref_same_group_adjacent"):
        with op.batch_alter_table("schedule_settings") as batch:
            batch.drop_column("pref_same_group_adjacent")


def _guess(name: str | None) -> str | None:
    from app.domain.subject_group import infer_subject_group_from_name

    return infer_subject_group_from_name(name or "")
