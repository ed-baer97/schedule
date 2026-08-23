"""Pure schedule conflict predicates (no Session / ORM)."""
from __future__ import annotations

from typing import Any


def time_intervals_overlap(
    start_a: Any, end_a: Any, start_b: Any, end_b: Any
) -> bool:
    """True if [start_a, end_a) overlaps [start_b, end_b)."""
    return start_a < end_b and start_b < end_a


def slots_conflict(
    *,
    day_a: int,
    lesson_a: int,
    interval_a: tuple[Any, Any] | None,
    day_b: int,
    lesson_b: int,
    interval_b: tuple[Any, Any] | None,
) -> bool:
    """
    True if two slots cannot occur at the same time.
    With intervals: overlap. Otherwise: same day and same lesson number.
    """
    if interval_a is not None and interval_b is not None:
        return time_intervals_overlap(
            interval_a[0], interval_a[1], interval_b[0], interval_b[1]
        )
    return day_a == day_b and lesson_a == lesson_b


def subject_day_limit_reached(placed_today: int, max_per_day: int) -> bool:
    return int(placed_today) >= int(max_per_day)


def teacher_class_day_limit_reached(placed_today: int, max_per_day: int = 2) -> bool:
    return int(placed_today) >= int(max_per_day)
