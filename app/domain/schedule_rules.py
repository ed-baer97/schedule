"""Pure schedule conflict predicates (no Session / ORM)."""
from __future__ import annotations

from typing import Any

from app.domain.schedule_facts import BusySlotFact, SlotFact, UnitFact


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


def slot_facts_conflict(a: SlotFact | BusySlotFact, b: SlotFact | BusySlotFact) -> bool:
    """True if two flat slot facts overlap in time."""
    return slots_conflict(
        day_a=a.day,
        lesson_a=a.lesson,
        interval_a=a.interval,
        day_b=b.day,
        lesson_b=b.lesson,
        interval_b=b.interval,
    )


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


def units_cannot_share_class_slot(a: UnitFact, b: UnitFact) -> bool:
    """
    True if two units must not occupy the same class grid slot together.
    Same assignment always conflicts; otherwise uses groups_can_share_slot.
    """
    if a.class_id != b.class_id:
        return False
    if a.assignment_id == b.assignment_id:
        return True
    return not groups_can_share_slot(
        a.group_number, b.group_number, a.subject_id, b.subject_id
    )


def occupancy_blocks_unit(
    unit: UnitFact,
    occupied: BusySlotFact,
    *,
    candidate_slot: SlotFact | BusySlotFact,
) -> bool:
    """
    True if an existing occupancy blocks placing ``unit`` at ``candidate_slot``.
    Requires same class on the occupancy (or None treated as same-class check skipped).
    """
    if occupied.class_id is not None and occupied.class_id != unit.class_id:
        return False
    if not slot_facts_conflict(candidate_slot, occupied):
        return False
    other = UnitFact(
        unit_id="occupied",
        assignment_id=occupied.assignment_id if occupied.assignment_id is not None else -1,
        teacher_id=None,
        class_id=unit.class_id,
        subject_id=occupied.subject_id,
        group_number=occupied.group_number,
        school_level=unit.school_level,
    )
    return units_cannot_share_class_slot(unit, other)


def teacher_busy_at_slot(
    slot: SlotFact | BusySlotFact,
    teacher_id: int | None,
    external_busy: dict[int, list[BusySlotFact]],
) -> bool:
    """True if teacher already has a busy fact overlapping ``slot``."""
    if not teacher_id:
        return False
    for busy in external_busy.get(teacher_id, []):
        if slot_facts_conflict(slot, busy):
            return True
    return False


def overlapping_classroom_busy(
    slot: SlotFact | BusySlotFact,
    classroom_id: int | None,
    classroom_busy: dict[int, list[BusySlotFact]],
) -> list[BusySlotFact]:
    """Busy facts for ``classroom_id`` that overlap ``slot``."""
    if not classroom_id:
        return []
    return [
        busy
        for busy in classroom_busy.get(classroom_id, [])
        if slot_facts_conflict(slot, busy)
    ]


def classroom_at_capacity(
    slot: SlotFact | BusySlotFact,
    classroom_id: int | None,
    classroom_busy: dict[int, list[BusySlotFact]],
    capacity: int,
) -> bool:
    """
    True if placing into ``classroom_id`` at ``slot`` would exceed capacity.
    Capacity is the max number of overlapping occupancies allowed.
    """
    if not classroom_id:
        return False
    cap = max(1, int(capacity))
    return len(overlapping_classroom_busy(slot, classroom_id, classroom_busy)) >= cap

