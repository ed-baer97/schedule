"""per-day bells + class hour on shift

Revision ID: 6day_bells
Revises: 5shift_bells
Create Date: 2026-03-29

"""
from alembic import op
import sqlalchemy as sa


revision = '6day_bells'
down_revision = '5shift_bells'
branch_labels = None
depends_on = None


def _sqlite_columns(conn, table):
    r = conn.execute(sa.text(f'PRAGMA table_info({table})'))
    return [row[1] for row in r.fetchall()]


def upgrade():
    conn = op.get_bind()

    cols_shifts = _sqlite_columns(conn, 'shifts')
    if 'class_hour_day' not in cols_shifts:
        op.add_column('shifts', sa.Column('class_hour_day', sa.Integer(), nullable=True))
    if 'class_hour_start' not in cols_shifts:
        op.add_column('shifts', sa.Column('class_hour_start', sa.Time(), nullable=True))
    if 'class_hour_end' not in cols_shifts:
        op.add_column('shifts', sa.Column('class_hour_end', sa.Time(), nullable=True))

    cols_slt = _sqlite_columns(conn, 'shift_lesson_times')
    has_day = 'day_of_week' in cols_slt
    if has_day:
        n_d2 = conn.execute(sa.text(
            'SELECT COUNT(*) FROM shift_lesson_times WHERE day_of_week = 2'
        )).scalar()
    else:
        n_d2 = 0

    # Уже есть строки по дням — только добиваем ограничение
    if has_day and n_d2:
        try:
            op.drop_constraint('uq_shift_lesson_time', 'shift_lesson_times', type_='unique')
        except Exception:
            pass
        try:
            op.drop_constraint('uq_shift_lesson_day', 'shift_lesson_times', type_='unique')
        except Exception:
            pass
        op.create_unique_constraint(
            'uq_shift_lesson_day', 'shift_lesson_times',
            ['shift_id', 'lesson_number', 'day_of_week'],
        )
        return

    # Пересобираем таблицу звонков: SQLite не снимает UNIQUE надёжно через drop_constraint
    if has_day:
        rows = conn.execute(sa.text("""
            SELECT shift_id, lesson_number, time_start, time_end
            FROM shift_lesson_times
            WHERE day_of_week IS NULL OR day_of_week = 1
        """)).fetchall()
    else:
        rows = conn.execute(sa.text("""
            SELECT shift_id, lesson_number, time_start, time_end FROM shift_lesson_times
        """)).fetchall()

    op.execute(sa.text('PRAGMA foreign_keys=OFF'))
    op.drop_table('shift_lesson_times')
    op.create_table(
        'shift_lesson_times',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('shift_id', sa.Integer(), nullable=False),
        sa.Column('day_of_week', sa.Integer(), nullable=False),
        sa.Column('lesson_number', sa.Integer(), nullable=False),
        sa.Column('time_start', sa.Time(), nullable=False),
        sa.Column('time_end', sa.Time(), nullable=False),
        sa.ForeignKeyConstraint(['shift_id'], ['shifts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('shift_id', 'lesson_number', 'day_of_week', name='uq_shift_lesson_day'),
    )
    op.execute(sa.text('PRAGMA foreign_keys=ON'))

    for shift_id, lesson_number, ts, te in rows:
        for d in range(1, 7):
            conn.execute(
                sa.text("""
                INSERT INTO shift_lesson_times (shift_id, day_of_week, lesson_number, time_start, time_end)
                VALUES (:sid, :d, :ln, :ts, :te)
                """),
                {'sid': shift_id, 'd': d, 'ln': lesson_number, 'ts': ts, 'te': te},
            )


def downgrade():
    conn = op.get_bind()
    try:
        op.drop_constraint('uq_shift_lesson_day', 'shift_lesson_times', type_='unique')
    except Exception:
        pass
    rows = conn.execute(sa.text(
        'SELECT shift_id, lesson_number, time_start, time_end FROM shift_lesson_times WHERE day_of_week = 1'
    )).fetchall()
    op.execute(sa.text('PRAGMA foreign_keys=OFF'))
    op.drop_table('shift_lesson_times')
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
    op.execute(sa.text('PRAGMA foreign_keys=ON'))
    for shift_id, lesson_number, ts, te in rows:
        conn.execute(
            sa.text("""
            INSERT INTO shift_lesson_times (shift_id, lesson_number, time_start, time_end)
            VALUES (:sid, :ln, :ts, :te)
            """),
            {'sid': shift_id, 'ln': lesson_number, 'ts': ts, 'te': te},
        )
    op.drop_column('shifts', 'class_hour_end')
    op.drop_column('shifts', 'class_hour_start')
    op.drop_column('shifts', 'class_hour_day')
