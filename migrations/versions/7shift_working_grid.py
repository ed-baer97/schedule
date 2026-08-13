"""move working_days and max_lessons_per_day to shifts

Revision ID: 7shift_grid
Revises: 6day_bells
Create Date: 2026-03-29

"""
from alembic import op
import sqlalchemy as sa


revision = '7shift_grid'
down_revision = '6day_bells'
branch_labels = None
depends_on = None


def _sqlite_columns(conn, table):
    r = conn.execute(sa.text(f'PRAGMA table_info({table})'))
    return [row[1] for row in r.fetchall()]


def upgrade():
    conn = op.get_bind()
    cols_shifts = _sqlite_columns(conn, 'shifts')

    if 'working_days' not in cols_shifts:
        op.add_column('shifts', sa.Column('working_days', sa.Integer(), nullable=True))
    if 'max_lessons_per_day' not in cols_shifts:
        op.add_column('shifts', sa.Column('max_lessons_per_day', sa.Integer(), nullable=True))

    conn.execute(sa.text("""
        UPDATE shifts SET
            working_days = COALESCE(
                (SELECT ss.working_days FROM schedule_settings ss
                 WHERE ss.school_level = shifts.school_level LIMIT 1),
                5
            ),
            max_lessons_per_day = COALESCE(
                (SELECT ss.max_lessons_per_day FROM schedule_settings ss
                 WHERE ss.school_level = shifts.school_level LIMIT 1),
                CASE WHEN shifts.school_level = 'elementary' THEN 5 ELSE 7 END
            )
    """))

    conn.execute(sa.text("""
        UPDATE shifts SET working_days = 5 WHERE working_days IS NULL
    """))
    conn.execute(sa.text("""
        UPDATE shifts SET max_lessons_per_day =
            CASE WHEN school_level = 'elementary' THEN 5 ELSE 7 END
        WHERE max_lessons_per_day IS NULL
    """))

    with op.batch_alter_table('shifts') as batch:
        batch.alter_column('working_days', nullable=False, server_default='5')
        batch.alter_column('max_lessons_per_day', nullable=False, server_default='7')

    cols_ss = _sqlite_columns(conn, 'schedule_settings')
    with op.batch_alter_table('schedule_settings') as batch:
        if 'working_days' in cols_ss:
            batch.drop_column('working_days')
        if 'max_lessons_per_day' in cols_ss:
            batch.drop_column('max_lessons_per_day')


def downgrade():
    op.add_column(
        'schedule_settings',
        sa.Column('working_days', sa.Integer(), server_default='5'),
    )
    op.add_column(
        'schedule_settings',
        sa.Column('max_lessons_per_day', sa.Integer(), server_default='7'),
    )
    conn = op.get_bind()
    conn.execute(sa.text("""
        UPDATE schedule_settings SET
            working_days = COALESCE(
                (SELECT MAX(s.working_days) FROM shifts s
                 WHERE s.school_level = schedule_settings.school_level),
                5
            ),
            max_lessons_per_day = COALESCE(
                (SELECT MAX(s.max_lessons_per_day) FROM shifts s
                 WHERE s.school_level = schedule_settings.school_level),
                7
            )
    """))
    with op.batch_alter_table('shifts') as batch:
        batch.drop_column('working_days')
        batch.drop_column('max_lessons_per_day')
