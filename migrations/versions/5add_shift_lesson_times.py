"""add shift_lesson_times for bell schedule

Revision ID: 5shift_bells
Revises: 4add_classes_cap
Create Date: 2026-03-29

"""
from alembic import op
import sqlalchemy as sa


revision = '5shift_bells'
down_revision = '4add_classes_cap'
branch_labels = None
depends_on = None


def _table_exists(connection, table):
    r = connection.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name=:t"),
        {"t": table},
    )
    return r.fetchone() is not None


def upgrade():
    conn = op.get_bind()
    if _table_exists(conn, 'shift_lesson_times'):
        return
    op.create_table(
        'shift_lesson_times',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shift_id', sa.Integer(), nullable=False),
        sa.Column('lesson_number', sa.Integer(), nullable=False),
        sa.Column('time_start', sa.Time(), nullable=False),
        sa.Column('time_end', sa.Time(), nullable=False),
        sa.ForeignKeyConstraint(['shift_id'], ['shifts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('shift_id', 'lesson_number', name='uq_shift_lesson_time'),
    )


def downgrade():
    op.drop_table('shift_lesson_times')
