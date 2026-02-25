"""add classes_capacity to classrooms

Revision ID: 4add_classes_cap
Revises: 3add_classroom
Create Date: 2026-02-22

"""
from alembic import op
import sqlalchemy as sa


revision = '4add_classes_cap'
down_revision = '3add_classroom'
branch_labels = None
depends_on = None


def _column_exists(connection, table, column):
    """Check if column exists (SQLite)"""
    result = connection.execute(sa.text("PRAGMA table_info(" + table + ")"))
    return any(row[1] == column for row in result)


def upgrade():
    conn = op.get_bind()
    if not _column_exists(conn, 'classrooms', 'classes_capacity'):
        op.add_column('classrooms', sa.Column('classes_capacity', sa.Integer(), server_default='1', nullable=False))


def downgrade():
    op.drop_column('classrooms', 'classes_capacity')
