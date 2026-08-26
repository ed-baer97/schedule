"""classroom_subjects M2M; drop classrooms.subject_id

Revision ID: 12classroom_subjects
Revises: 11classroom_subject
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from migrations.schema_util import column_exists, table_exists

revision = "12classroom_subjects"
down_revision = "11classroom_subject"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if not table_exists(conn, "classroom_subjects"):
        op.create_table(
            "classroom_subjects",
            sa.Column(
                "classroom_id",
                sa.Integer(),
                sa.ForeignKey("classrooms.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column(
                "subject_id",
                sa.Integer(),
                sa.ForeignKey("subjects.id", ondelete="CASCADE"),
                primary_key=True,
            ),
        )

    if column_exists(conn, "classrooms", "subject_id"):
        conn.execute(
            sa.text(
                """
                INSERT INTO classroom_subjects (classroom_id, subject_id)
                SELECT c.id, c.subject_id
                FROM classrooms c
                WHERE c.subject_id IS NOT NULL
                  AND NOT EXISTS (
                    SELECT 1
                    FROM classroom_subjects cs
                    WHERE cs.classroom_id = c.id
                      AND cs.subject_id = c.subject_id
                  )
                """
            )
        )
        op.drop_column("classrooms", "subject_id")


def downgrade() -> None:
    conn = op.get_bind()
    if not column_exists(conn, "classrooms", "subject_id"):
        op.add_column(
            "classrooms",
            sa.Column("subject_id", sa.Integer(), nullable=True),
        )
    if table_exists(conn, "classroom_subjects"):
        conn.execute(
            sa.text(
                """
                UPDATE classrooms
                SET subject_id = (
                    SELECT cs.subject_id
                    FROM classroom_subjects cs
                    WHERE cs.classroom_id = classrooms.id
                    ORDER BY cs.subject_id
                    LIMIT 1
                )
                WHERE subject_id IS NULL
                """
            )
        )
        op.drop_table("classroom_subjects")
