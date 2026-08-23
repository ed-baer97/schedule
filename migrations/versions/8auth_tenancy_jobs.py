"""Auth + multi-tenant + jobs migration.

Revision ID: 8auth_tenancy
Revises: 7shift_grid
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "8auth_tenancy"
down_revision = "7shift_grid"
branch_labels = None
depends_on = None

_DOMAIN_TABLES = (
    "teachers",
    "classrooms",
    "school_classes",
    "shifts",
    "subjects",
    "teaching_assignments",
    "schedule_cells",
    "schedule_settings",
    "shift_lesson_times",
)


def upgrade() -> None:
    op.create_table(
        "schools",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("slug"),
    )
    op.execute(
        sa.text(
            "INSERT INTO schools (id, name, slug, is_active) "
            "VALUES (1, 'Школа по умолчанию', 'default', 1)"
        )
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("school_id", sa.Integer(), sa.ForeignKey("schools.id"), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "invite_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("school_id", sa.Integer(), sa.ForeignKey("schools.id"), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("token"),
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("school_id", sa.Integer(), sa.ForeignKey("schools.id"), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("progress", sa.Text(), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("celery_task_id", sa.String(64), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_jobs_school_id", "jobs", ["school_id"])
    op.create_index("ix_jobs_status", "jobs", ["status"])

    bind = op.get_bind()
    insp = sa.inspect(bind)
    dialect = bind.dialect.name

    for table in _DOMAIN_TABLES:
        if table not in insp.get_table_names():
            continue
        cols = {c["name"] for c in insp.get_columns(table)}
        if "school_id" in cols:
            continue
        op.add_column(table, sa.Column("school_id", sa.Integer(), nullable=True))
        op.execute(sa.text(f"UPDATE {table} SET school_id = 1 WHERE school_id IS NULL"))
        if dialect == "sqlite":
            # SQLite: leave nullable; app always sets school_id. Batch recreate is heavy.
            op.create_index(f"ix_{table}_school_id", table, ["school_id"])
        else:
            op.alter_column(table, "school_id", nullable=False)
            op.create_foreign_key(
                f"fk_{table}_school_id", table, "schools", ["school_id"], ["id"]
            )
            op.create_index(f"ix_{table}_school_id", table, ["school_id"])

    # schedule_settings: drop unique(school_level), add unique(school_id, school_level)
    if "schedule_settings" in insp.get_table_names():
        if dialect == "sqlite":
            with op.batch_alter_table("schedule_settings") as batch:
                batch.create_unique_constraint(
                    "uq_schedule_settings_school_level",
                    ["school_id", "school_level"],
                )
        else:
            try:
                op.drop_constraint("schedule_settings_school_level_key", "schedule_settings")
            except Exception:
                try:
                    op.drop_constraint("uq_schedule_settings_school_level", "schedule_settings")
                except Exception:
                    pass
            # drop old unique on school_level alone if named differently
            try:
                op.drop_constraint("school_level", "schedule_settings", type_="unique")
            except Exception:
                pass
            op.create_unique_constraint(
                "uq_schedule_settings_school_level",
                "schedule_settings",
                ["school_id", "school_level"],
            )


def downgrade() -> None:
    op.drop_table("jobs")
    op.drop_table("invite_tokens")
    op.drop_table("users")
    for table in reversed(_DOMAIN_TABLES):
        try:
            op.drop_index(f"ix_{table}_school_id", table_name=table)
        except Exception:
            pass
        try:
            op.drop_column(table, "school_id")
        except Exception:
            pass
    op.drop_table("schools")
