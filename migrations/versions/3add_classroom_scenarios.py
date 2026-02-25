"""add classroom scenarios (teacher_room, class_room, fixed subjects)

Revision ID: 3add_classroom
Revises: 2add_max_subject
Create Date: 2026-02-20

"""
from alembic import op
import sqlalchemy as sa


revision = '3add_classroom'
down_revision = '2add_max_subject'
branch_labels = None
depends_on = None


def _column_exists(connection, table, column):
    """Check if column exists (SQLite)"""
    result = connection.execute(sa.text("PRAGMA table_info(" + table + ")"))
    return any(row[1] == column for row in result)


def upgrade():
    conn = op.get_bind()
    if not _column_exists(conn, 'subjects', 'requires_fixed_classroom'):
        op.add_column('subjects', sa.Column('requires_fixed_classroom', sa.Boolean(), server_default='0'))
    if not _column_exists(conn, 'subjects', 'default_classroom_id'):
        op.add_column('subjects', sa.Column('default_classroom_id', sa.Integer(), sa.ForeignKey('classrooms.id'), nullable=True))
    if not _column_exists(conn, 'teachers', 'home_classroom_id'):
        op.add_column('teachers', sa.Column('home_classroom_id', sa.Integer(), sa.ForeignKey('classrooms.id'), nullable=True))
    if not _column_exists(conn, 'school_classes', 'home_classroom_id'):
        op.add_column('school_classes', sa.Column('home_classroom_id', sa.Integer(), sa.ForeignKey('classrooms.id'), nullable=True))
    if not _column_exists(conn, 'schedule_settings', 'classroom_mode'):
        op.add_column('schedule_settings', sa.Column('classroom_mode', sa.String(20), server_default='class_room'))
    if not _column_exists(conn, 'schedule_settings', 'elementary_group_subjects_leave'):
        op.add_column('schedule_settings', sa.Column('elementary_group_subjects_leave', sa.Boolean(), server_default='1'))


def downgrade():
    op.drop_column('schedule_settings', 'elementary_group_subjects_leave')
    op.drop_column('schedule_settings', 'classroom_mode')
    op.drop_column('school_classes', 'home_classroom_id')
    op.drop_column('teachers', 'home_classroom_id')
    op.drop_column('subjects', 'default_classroom_id')
    op.drop_column('subjects', 'requires_fixed_classroom')
