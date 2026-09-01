"""Per-day lesson counts on a shift (class-hour day may be shorter)."""

from types import SimpleNamespace

from app.domain.shift_grid import (
    lesson_end_exclusive,
    lessons_count_on_day,
    weekly_slot_count,
)


def test_class_hour_day_uses_shorter_count() -> None:
    shift = SimpleNamespace(
        start_lesson=1,
        lessons_count=6,
        working_days=5,
        class_hour_day=1,
        class_hour_lessons_count=4,
    )
    assert lessons_count_on_day(shift, 1) == 4
    assert lessons_count_on_day(shift, 2) == 6
    assert lesson_end_exclusive(shift, 1) == 5
    assert lesson_end_exclusive(shift, 2) == 7
    assert lesson_end_exclusive(shift) == 7
    assert weekly_slot_count(shift) == 4 + 6 * 4


def test_missing_class_hour_count_keeps_full_day() -> None:
    shift = SimpleNamespace(
        start_lesson=1,
        lessons_count=6,
        working_days=5,
        class_hour_day=1,
        class_hour_lessons_count=None,
    )
    assert lessons_count_on_day(shift, 1) == 6
    assert weekly_slot_count(shift) == 30
