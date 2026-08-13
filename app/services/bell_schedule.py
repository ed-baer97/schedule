"""
Bell schedule: resolve lesson time intervals per shift and day for conflict detection.
"""
from sqlalchemy.orm import Session

from app.models import Shift, ShiftLessonTime
from app.services.session_util import resolve_session


def get_interval_for_slot(shift_id, lesson_number, day_of_week, session: Session | None = None):
    """
    Return (time_start, time_end) for a slot, else None.
    lesson_number 0 = классный час (время из Shift, только в class_hour_day).
    """
    if not shift_id or not day_of_week:
        return None
    s = resolve_session(session)
    shift = s.get(Shift, shift_id)
    if not shift:
        return None
    if lesson_number == 0:
        if (
            shift.class_hour_day == day_of_week
            and shift.class_hour_start
            and shift.class_hour_end
        ):
            return (shift.class_hour_start, shift.class_hour_end)
        return None
    row = (
        s.query(ShiftLessonTime)
        .filter_by(
            shift_id=shift_id,
            lesson_number=lesson_number,
            day_of_week=day_of_week,
        )
        .first()
    )
    if not row:
        return None
    return (row.time_start, row.time_end)


def schedules_conflict(
    shift_id_a, lesson_a, day_a, shift_id_b, lesson_b, day_b, session: Session | None = None
):
    """
    True if two slots cannot occur at the same time.
    With intervals: overlap. Otherwise: same day and same lesson number.
    """
    ia = get_interval_for_slot(shift_id_a, lesson_a, day_a, session=session)
    ib = get_interval_for_slot(shift_id_b, lesson_b, day_b, session=session)
    if ia is not None and ib is not None:
        start_a, end_a = ia
        start_b, end_b = ib
        return start_a < end_b and start_b < end_a
    return day_a == day_b and lesson_a == lesson_b
