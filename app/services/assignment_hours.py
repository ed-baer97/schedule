"""Batch helpers for scheduled / remaining hours (avoids model @property SQL)."""
from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.domain.assignment import remaining_hours as domain_remaining
from app.domain.schedule_variant import (
    KIND_MAIN,
    KIND_MONTHLY,
    is_monthly_only_hours,
    normalize_variant,
)
from app.models import ScheduleCell, TeachingAssignment
from app.services.schedule_scope import variant_filter


def _scope(
    *,
    schedule_kind: str | None = KIND_MAIN,
    week_index: int | None = 0,
    across_monthly_weeks: bool = False,
):
    return variant_filter(
        schedule_kind,
        week_index,
        across_monthly_weeks=across_monthly_weeks,
    )


def placed_counts(
    db: Session,
    assignment_ids: list[int] | None = None,
    *,
    schedule_kind: str | None = KIND_MAIN,
    week_index: int | None = 0,
    across_monthly_weeks: bool = False,
) -> dict[int, int]:
    """Return {assignment_id: cell_count} for the given ids (or empty)."""
    if not assignment_ids:
        return {}
    rows = db.execute(
        select(ScheduleCell.assignment_id, func.count())
        .where(
            ScheduleCell.assignment_id.in_(assignment_ids),
            _scope(
                schedule_kind=schedule_kind,
                week_index=week_index,
                across_monthly_weeks=across_monthly_weeks,
            ),
        )
        .group_by(ScheduleCell.assignment_id)
    ).all()
    return {int(aid): int(cnt) for aid, cnt in rows}


def placed_count(
    db: Session,
    assignment_id: int,
    *,
    schedule_kind: str | None = KIND_MAIN,
    week_index: int | None = 0,
    across_monthly_weeks: bool = False,
) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(ScheduleCell)
            .where(
                ScheduleCell.assignment_id == assignment_id,
                _scope(
                    schedule_kind=schedule_kind,
                    week_index=week_index,
                    across_monthly_weeks=across_monthly_weeks,
                ),
            )
        )
        or 0
    )


def placed_counts_except_day(
    db: Session,
    assignment_ids: list[int],
    day: int,
    *,
    max_lesson: int | None = None,
    schedule_kind: str | None = KIND_MAIN,
    week_index: int | None = 0,
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
            _scope(schedule_kind=schedule_kind, week_index=week_index),
        )
        .group_by(ScheduleCell.assignment_id)
    ).all()
    return {int(aid): int(cnt) for aid, cnt in rows}


def placed_counts_on_day_after_lesson(
    db: Session,
    assignment_ids: list[int],
    day: int,
    after_lesson: int,
    *,
    schedule_kind: str | None = KIND_MAIN,
    week_index: int | None = 0,
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
            _scope(schedule_kind=schedule_kind, week_index=week_index),
        )
        .group_by(ScheduleCell.assignment_id)
    ).all()
    return {int(aid): int(cnt) for aid, cnt in rows}


def placed_lessons_by_assignment_day(
    db: Session,
    assignment_ids: list[int],
    *,
    schedule_kind: str | None = KIND_MAIN,
    week_index: int | None = 0,
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
        .where(
            ScheduleCell.assignment_id.in_(assignment_ids),
            _scope(schedule_kind=schedule_kind, week_index=week_index),
        )
        .group_by(ScheduleCell.assignment_id, ScheduleCell.day_of_week)
    ).all()
    return {(int(aid), int(day)): int(n) for aid, day, n in rows}


def occupancy_lessons_by_class_day(
    db: Session,
    class_ids: list[int],
    *,
    schedule_kind: str | None = KIND_MAIN,
    week_index: int | None = 0,
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
        .where(
            ScheduleCell.class_id.in_(class_ids),
            _scope(schedule_kind=schedule_kind, week_index=week_index),
        )
        .group_by(ScheduleCell.class_id, ScheduleCell.day_of_week)
    ).all()
    return {(int(cid), int(day)): int(n) for cid, day, n in rows}


def remaining_for(
    assignment: TeachingAssignment,
    *,
    db: Session | None = None,
    placed: int | None = None,
    schedule_kind: str | None = KIND_MAIN,
    week_index: int | None = 0,
) -> float:
    """Remaining hours for one assignment (explicit placed count or DB count)."""
    kind, week = normalize_variant(schedule_kind, week_index)
    hours = assignment.hours_per_week
    if placed is None:
        if db is not None:
            if is_monthly_only_hours(hours) and kind == KIND_MONTHLY:
                placed = placed_count(
                    db,
                    assignment.id,
                    schedule_kind=KIND_MONTHLY,
                    across_monthly_weeks=True,
                )
            else:
                placed = placed_count(
                    db, assignment.id, schedule_kind=kind, week_index=week
                )
        else:
            q = assignment.schedule_cells.filter(
                ScheduleCell.schedule_kind == kind,
            )
            if not (is_monthly_only_hours(hours) and kind == KIND_MONTHLY):
                q = q.filter(ScheduleCell.week_index == week)
            placed = q.count()
    return domain_remaining(hours, placed, schedule_kind=kind)


def remaining_by_assignment(
    db: Session,
    assignments: Iterable[TeachingAssignment],
    *,
    schedule_kind: str | None = KIND_MAIN,
    week_index: int | None = 0,
) -> dict[int, float]:
    """Remaining hours keyed by assignment id, using the correct placement scope."""
    kind, week = normalize_variant(schedule_kind, week_index)
    items = list(assignments)
    weekly_ids = [a.id for a in items if not is_monthly_only_hours(a.hours_per_week)]
    monthly_ids = [a.id for a in items if is_monthly_only_hours(a.hours_per_week)]
    weekly_placed = placed_counts(
        db, weekly_ids, schedule_kind=kind, week_index=week
    )
    monthly_placed: dict[int, int] = {}
    if kind == KIND_MONTHLY and monthly_ids:
        monthly_placed = placed_counts(
            db,
            monthly_ids,
            schedule_kind=KIND_MONTHLY,
            across_monthly_weeks=True,
        )
    result: dict[int, float] = {}
    for assignment in items:
        if is_monthly_only_hours(assignment.hours_per_week):
            placed = monthly_placed.get(assignment.id, 0)
        else:
            placed = weekly_placed.get(assignment.id, 0)
        result[int(assignment.id)] = domain_remaining(
            assignment.hours_per_week, placed, schedule_kind=kind
        )
    return result
