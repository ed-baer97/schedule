"""Pure helpers for teaching-assignment hours (no Session)."""
from __future__ import annotations

from app.domain.schedule_variant import (
    KIND_MONTHLY,
    HOURS_STEP,
    is_monthly_only_hours,
    monthly_quota_lessons,
    snap_hours,
)


def remaining_hours(
    hours_per_week: float | int,
    placed: int,
    *,
    schedule_kind: str = "main",
) -> float:
    hours = snap_hours(hours_per_week)
    placed_n = int(placed)
    if is_monthly_only_hours(hours):
        if schedule_kind != KIND_MONTHLY:
            return 0.0
        leftover = monthly_quota_lessons(hours) - placed_n
        return max(0.0, leftover * HOURS_STEP)
    return max(0.0, hours - placed_n)


def hours_exhausted(
    hours_per_week: float | int,
    placed: int,
    *,
    schedule_kind: str = "main",
) -> bool:
    return remaining_hours(
        hours_per_week, placed, schedule_kind=schedule_kind
    ) <= 0
