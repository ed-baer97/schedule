"""
Bell schedule: resolve lesson time intervals per shift and day for conflict detection.
"""
from sqlalchemy.orm import Session

from app.domain.schedule_rules import slots_conflict
from app.models import Shift, ShiftLessonTime


def get_interval_for_slot(shift_id, lesson_number, day_of_week, session: Session):
    """
    Return (time_start, time_end) for a slot, else None.
    lesson_number 0 = классный час (время из Shift, только в class_hour_day).
    """
    if not shift_id or not day_of_week:
        return None
    s = session
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
    shift_id_a, lesson_a, day_a, shift_id_b, lesson_b, day_b, session: Session
):
    """
    True if two slots cannot occur at the same time.
    With intervals: overlap. Otherwise: same day and same lesson number.
    """
    ia = get_interval_for_slot(shift_id_a, lesson_a, day_a, session=session)
    ib = get_interval_for_slot(shift_id_b, lesson_b, day_b, session=session)
    return slots_conflict(
        day_a=day_a,
        lesson_a=lesson_a,
        interval_a=ia,
        day_b=day_b,
        lesson_b=lesson_b,
        interval_b=ib,
    )
