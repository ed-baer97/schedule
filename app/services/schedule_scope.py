"""SQLAlchemy filters for schedule grid variants."""
from __future__ import annotations

from sqlalchemy import and_

from app.domain.schedule_variant import (
    KIND_MAIN,
    KIND_MONTHLY,
    MONTHLY_WEEKS,
    normalize_variant,
)
from app.models import ScheduleCell


def variant_filter(
    kind: str | None = KIND_MAIN,
    week: int | None = 0,
    *,
    across_monthly_weeks: bool = False,
):
    if across_monthly_weeks:
        kind, _ = normalize_variant(kind or KIND_MONTHLY, 1)
        return and_(
            ScheduleCell.schedule_kind == KIND_MONTHLY,
            ScheduleCell.week_index.in_(MONTHLY_WEEKS),
        )
    kind, week = normalize_variant(kind, week)
    return and_(
        ScheduleCell.schedule_kind == kind,
        ScheduleCell.week_index == week,
    )
