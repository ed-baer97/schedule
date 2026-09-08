"""Batch helpers for scheduled / remaining hours (avoids model @property SQL)."""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.domain.assignment import remaining_hours as domain_remaining
from app.models import ScheduleCell, TeachingAssignment


def placed_counts(
    db: Session, assignment_ids: list[int] | None = None
) -> dict[int, int]:
    """Return {assignment_id: cell_count} for the given ids (or empty)."""
    if not assignment_ids:
        return {}
    rows = db.execute(
        select(ScheduleCell.assignment_id, func.count())
        .where(ScheduleCell.assignment_id.in_(assignment_ids))
        .group_by(ScheduleCell.assignment_id)
    ).all()
    return {int(aid): int(cnt) for aid, cnt in rows}


def placed_count(db: Session, assignment_id: int) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(ScheduleCell)
            .where(ScheduleCell.assignment_id == assignment_id)
        )
        or 0
    )


def placed_counts_except_day(
    db: Session,
    assignment_ids: list[int],
    day: int,
    *,
    max_lesson: int | None = None,
) -> dict[int, int]:
    """Placed hours per assignment, ignoring the rebuild window on ``day``.

    With ``max_lesson``, only cells ``lesson_number <= max_lesson`` on that day
    are treated as unplaced (later lessons stay as already placed).
    """
    if not assignment_ids:
        return {}
    cond = ScheduleCell.day_of_week != int(day)
    if max_lesson is not None:
        cond = or_(cond, ScheduleCell.lesson_number > int(max_lesson))
    rows = db.execute(
        select(ScheduleCell.assignment_id, func.count())
        .where(
            ScheduleCell.assignment_id.in_(assignment_ids),
            cond,
        )
        .group_by(ScheduleCell.assignment_id)
    ).all()
    return {int(aid): int(cnt) for aid, cnt in rows}


def placed_counts_on_day_after_lesson(
    db: Session, assignment_ids: list[int], day: int, after_lesson: int
) -> dict[int, int]:
    """Hours already on ``day`` with ``lesson_number > after_lesson`` (locked late slots)."""
    if not assignment_ids:
        return {}
    rows = db.execute(
        select(ScheduleCell.assignment_id, func.count())
        .where(
            ScheduleCell.assignment_id.in_(assignment_ids),
            ScheduleCell.day_of_week == int(day),
            ScheduleCell.lesson_number > int(after_lesson),
        )
        .group_by(ScheduleCell.assignment_id)
    ).all()
    return {int(aid): int(cnt) for aid, cnt in rows}


def placed_lessons_by_assignment_day(
    db: Session, assignment_ids: list[int]
) -> dict[tuple[int, int], int]:
    """{(assignment_id, day_of_week): distinct lessons}."""
    if not assignment_ids:
        return {}
    rows = db.execute(
        select(
            ScheduleCell.assignment_id,
            ScheduleCell.day_of_week,
            func.count(func.distinct(ScheduleCell.lesson_number)),
        )
        .where(ScheduleCell.assignment_id.in_(assignment_ids))
        .group_by(ScheduleCell.assignment_id, ScheduleCell.day_of_week)
    ).all()
    return {(int(aid), int(day)): int(n) for aid, day, n in rows}


def occupancy_lessons_by_class_day(
    db: Session, class_ids: list[int]
) -> dict[tuple[int, int], int]:
    """{(class_id, day_of_week): distinct occupied lesson numbers}."""
    if not class_ids:
        return {}
    rows = db.execute(
        select(
            ScheduleCell.class_id,
            ScheduleCell.day_of_week,
            func.count(func.distinct(ScheduleCell.lesson_number)),
        )
        .where(ScheduleCell.class_id.in_(class_ids))
        .group_by(ScheduleCell.class_id, ScheduleCell.day_of_week)
    ).all()
    return {(int(cid), int(day)): int(n) for cid, day, n in rows}


def remaining_for(
    assignment: TeachingAssignment,
    *,
    db: Session | None = None,
    placed: int | None = None,
) -> int:
    """Remaining hours for one assignment (explicit placed count or DB count)."""
    if placed is None:
        if db is not None:
            placed = placed_count(db, assignment.id)
        else:
            # Fallback for mid-solver after flush: relationship count
            placed = assignment.schedule_cells.count()
    return domain_remaining(assignment.hours_per_week, placed)
