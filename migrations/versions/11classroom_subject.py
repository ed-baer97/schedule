"""classroom subject_id + is_exclusive; drop subjects.default_classroom_id

Revision ID: 11classroom_subject
Revises: 10homeroom_teacher
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "11classroom_subject"
down_revision = "10homeroom_teacher"
branch_labels = None
depends_on = None


def _column_exists(connection, table: str, column: str) -> bool:
    result = connection.execute(sa.text(f"PRAGMA table_info({table})"))
    return any(row[1] == column for row in result)


def upgrade() -> None:
    conn = op.get_bind()

    if not _column_exists(conn, "classrooms", "subject_id"):
        op.add_column(
            "classrooms",
            sa.Column("subject_id", sa.Integer(), nullable=True),
        )
    if not _column_exists(conn, "classrooms", "is_exclusive"):
        op.add_column(
            "classrooms",
            sa.Column(
                "is_exclusive",
                sa.Boolean(),
                nullable=False,
                server_default="0",
            ),
        )

    if _column_exists(conn, "subjects", "default_classroom_id"):
        rows = conn.execute(
            sa.text(
                """
                SELECT id, default_classroom_id, requires_fixed_classroom
                FROM subjects
                WHERE default_classroom_id IS NOT NULL
                """
            )
        ).fetchall()
        for subject_id, classroom_id, requires_fixed in rows:
            existing = conn.execute(
                sa.text("SELECT subject_id FROM classrooms WHERE id = :cid"),
                {"cid": classroom_id},
            ).fetchone()
            if existing is None:
                continue
            if existing[0] is not None and existing[0] != subject_id:
                continue
            exclusive = 1 if requires_fixed else 0
            conn.execute(
                sa.text(
                    """
                    UPDATE classrooms
                    SET subject_id = :sid, is_exclusive = :excl
                    WHERE id = :cid
                    """
                ),
                {"sid": subject_id, "excl": exclusive, "cid": classroom_id},
            )
        op.drop_column("subjects", "default_classroom_id")


def downgrade() -> None:
    conn = op.get_bind()
    if not _column_exists(conn, "subjects", "default_classroom_id"):
        op.add_column(
            "subjects",
            sa.Column("default_classroom_id", sa.Integer(), nullable=True),
        )
    if _column_exists(conn, "classrooms", "subject_id"):
        rows = conn.execute(
            sa.text(
                """
                SELECT id, subject_id
                FROM classrooms
                WHERE subject_id IS NOT NULL
                """
            )
        ).fetchall()
        for classroom_id, subject_id in rows:
            conn.execute(
                sa.text(
                    """
                    UPDATE subjects
                    SET default_classroom_id = :cid
                    WHERE id = :sid AND default_classroom_id IS NULL
                    """
                ),
                {"cid": classroom_id, "sid": subject_id},
            )
        op.drop_column("classrooms", "subject_id")
    if _column_exists(conn, "classrooms", "is_exclusive"):
        op.drop_column("classrooms", "is_exclusive")
