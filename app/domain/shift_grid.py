"""Lesson counts per weekday for a shift (class-hour day may be shorter)."""

from __future__ import annotations

from typing import Any


def lessons_count_on_day(shift: Any, day: int) -> int:
    """How many regular lessons the shift has on this weekday (1–6)."""
    total = max(1, int(getattr(shift, "lessons_count", 6) or 6))
    class_day = getattr(shift, "class_hour_day", None)
    class_count = getattr(shift, "class_hour_lessons_count", None)
    if class_day and int(class_day) == int(day) and class_count:
        return max(1, min(total, int(class_count)))
    return total


def lesson_end_exclusive(shift: Any, day: int | None = None) -> int:
    """First lesson number *not* in the grid. ``day=None`` uses the full count."""
    start = max(1, int(getattr(shift, "start_lesson", 1) or 1))
    if day is None:
        return start + max(1, int(getattr(shift, "lessons_count", 6) or 6))
    return start + lessons_count_on_day(shift, day)


def weekly_slot_count(shift: Any) -> int:
    """Total regular-lesson slots in the shift week (class-hour day may subtract)."""
    wd = max(1, min(6, int(getattr(shift, "working_days", 5) or 5)))
    return sum(lessons_count_on_day(shift, d) for d in range(1, wd + 1))
