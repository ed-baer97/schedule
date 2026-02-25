"""add max_lessons_per_subject_per_day

Revision ID: 2add_max_subject
Revises: 1cf906308b3c
Create Date: 2026-02-20

"""
from alembic import op
import sqlalchemy as sa


revision = '2add_max_subject'
down_revision = '1cf906308b3c'
branch_labels = None
depends_on = None


def _column_exists(connection, table, column):
    """Check if column exists (SQLite)"""
    result = connection.execute(sa.text(
        "PRAGMA table_info(:table)"
    ), {"table": table})
    return any(row[1] == column for row in result)


def upgrade():
    conn = op.get_bind()
    if not _column_exists(conn, 'schedule_settings', 'max_lessons_per_subject_per_day'):
        op.add_column('schedule_settings',
            sa.Column('max_lessons_per_subject_per_day', sa.Integer(), server_default='2'))


def downgrade():
    op.drop_column('schedule_settings', 'max_lessons_per_subject_per_day')
