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


def groups_can_share_slot(
    group_a: int | None,
    group_b: int | None,
    subject_id_a: int | None = None,
    subject_id_b: int | None = None,
) -> bool:
    """
    True if two assignments may occupy the same (class, day, lesson) slot.

    Whole-class lessons (group None) conflict with everything.
    Same group number conflicts. Different groups of the same subject may share.
    Different subjects with different groups conflict (cannot share the class).
    """
    if group_a is None or group_b is None:
        return False
    if group_a == group_b:
        return False
    if subject_id_a is not None and subject_id_b is not None and subject_id_a != subject_id_b:
        return False
    return True

