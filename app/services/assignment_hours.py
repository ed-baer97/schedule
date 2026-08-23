"""Batch helpers for scheduled / remaining hours (avoids model @property SQL)."""
from __future__ import annotations

from sqlalchemy import func, select
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
