"""Pure domain helpers (no Session, no FastAPI)."""
from app.domain.assignment import hours_exhausted, remaining_hours
from app.domain.days import DAY_NAMES, SHORT_DAY_NAMES, fmt_time, time_range_label
from app.domain.schedule_rules import (
    slots_conflict,
    subject_day_limit_reached,
    teacher_class_day_limit_reached,
    time_intervals_overlap,
)
from app.domain.school_class import grade_from_name

__all__ = [
    "DAY_NAMES",
    "SHORT_DAY_NAMES",
    "fmt_time",
    "time_range_label",
    "grade_from_name",
    "remaining_hours",
    "hours_exhausted",
    "slots_conflict",
    "time_intervals_overlap",
    "subject_day_limit_reached",
    "teacher_class_day_limit_reached",
]
