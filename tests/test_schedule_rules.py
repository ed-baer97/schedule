"""Unit tests for shared schedule conflict predicates (no DB)."""
from datetime import time

from app.domain.schedule_facts import BusySlotFact, SlotFact, UnitFact
from app.domain.schedule_rules import (
    classroom_at_capacity,
    groups_can_share_slot,
    occupancy_blocks_unit,
    slot_facts_conflict,
    teacher_busy_at_slot,
    units_cannot_share_class_slot,
)


def _unit(**kwargs) -> UnitFact:
    base = dict(
        unit_id="u1",
        assignment_id=1,
        teacher_id=10,
        class_id=100,
        subject_id=5,
        group_number=None,
        school_level="elementary",
    )
    base.update(kwargs)
    return UnitFact(**base)


def test_same_assignment_cannot_share_slot():
    a = _unit(unit_id="a1", assignment_id=1)
    b = _unit(unit_id="a2", assignment_id=1)
    assert units_cannot_share_class_slot(a, b) is True


def test_different_groups_same_subject_can_share():
    a = _unit(assignment_id=1, group_number=1, subject_id=5)
    b = _unit(assignment_id=2, group_number=2, subject_id=5)
    assert units_cannot_share_class_slot(a, b) is False
    assert groups_can_share_slot(1, 2, 5, 5) is True


def test_different_subjects_groups_conflict():
    a = _unit(assignment_id=1, group_number=1, subject_id=5)
    b = _unit(assignment_id=2, group_number=2, subject_id=9)
    assert units_cannot_share_class_slot(a, b) is True


def test_whole_class_conflicts_with_group():
    a = _unit(assignment_id=1, group_number=None)
    b = _unit(assignment_id=2, group_number=1)
    assert units_cannot_share_class_slot(a, b) is True


def test_different_classes_do_not_conflict():
    a = _unit(class_id=1)
    b = _unit(class_id=2, assignment_id=2)
    assert units_cannot_share_class_slot(a, b) is False


def test_occupancy_blocks_unit_on_overlap():
    unit = _unit(group_number=None, subject_id=5)
    slot = SlotFact(
        slot_id="c100:d1:l2",
        class_id=100,
        day=1,
        lesson=2,
        shift_id=1,
        interval=None,
    )
    occupied = BusySlotFact(
        shift_id=1,
        day=1,
        lesson=2,
        interval=None,
        assignment_id=99,
        subject_id=5,
        group_number=None,
        class_id=100,
    )
    assert occupancy_blocks_unit(unit, occupied, candidate_slot=slot) is True


def test_teacher_busy_at_slot():
    slot = SlotFact(
        slot_id="c1:d1:l3",
        class_id=1,
        day=1,
        lesson=3,
        shift_id=1,
        interval=None,
    )
    busy = {
        10: [BusySlotFact(shift_id=2, day=1, lesson=3, interval=None)],
    }
    assert teacher_busy_at_slot(slot, 10, busy) is True
    assert teacher_busy_at_slot(slot, 11, busy) is False


def test_slot_facts_conflict_overlapping_intervals_different_lessons():
    """Same day, different lesson numbers, overlapping bell times → conflict."""
    a = SlotFact(
        slot_id="c1:d1:l2",
        class_id=1,
        day=1,
        lesson=2,
        shift_id=1,
        interval=(time(9, 0), time(9, 45)),
    )
    b = BusySlotFact(
        shift_id=2,
        day=1,
        lesson=5,
        interval=(time(9, 20), time(10, 5)),
    )
    assert slot_facts_conflict(a, b) is True


def test_slot_facts_conflict_non_overlapping_intervals():
    a = SlotFact(
        slot_id="c1:d1:l2",
        class_id=1,
        day=1,
        lesson=2,
        shift_id=1,
        interval=(time(9, 0), time(9, 45)),
    )
    b = BusySlotFact(
        shift_id=2,
        day=1,
        lesson=3,
        interval=(time(9, 45), time(10, 30)),
    )
    assert slot_facts_conflict(a, b) is False


def test_teacher_busy_at_slot_interval_overlap():
    slot = SlotFact(
        slot_id="c1:d1:l2",
        class_id=1,
        day=1,
        lesson=2,
        shift_id=1,
        interval=(time(9, 0), time(9, 45)),
    )
    busy = {
        10: [
            BusySlotFact(
                shift_id=2,
                day=1,
                lesson=7,
                interval=(time(9, 15), time(10, 0)),
            )
        ],
    }
    assert teacher_busy_at_slot(slot, 10, busy) is True
    assert teacher_busy_at_slot(slot, 11, busy) is False


def test_classroom_at_capacity_cap1():
    slot = SlotFact(
        slot_id="c1:d1:l2",
        class_id=1,
        day=1,
        lesson=2,
        shift_id=1,
        interval=None,
    )
    busy = {
        50: [
            BusySlotFact(
                shift_id=1,
                day=1,
                lesson=2,
                interval=None,
                classroom_id=50,
                source_cell_id=1,
            )
        ],
    }
    assert classroom_at_capacity(slot, 50, busy, capacity=1) is True
    assert classroom_at_capacity(slot, 50, busy, capacity=2) is False


def test_classroom_at_capacity_cap2_not_full():
    slot = SlotFact(
        slot_id="c1:d1:l2",
        class_id=1,
        day=1,
        lesson=2,
        shift_id=1,
        interval=(time(9, 0), time(9, 45)),
    )
    busy = {
        50: [
            BusySlotFact(
                shift_id=1,
                day=1,
                lesson=2,
                interval=(time(9, 0), time(9, 45)),
                classroom_id=50,
            )
        ],
    }
    assert classroom_at_capacity(slot, 50, busy, capacity=2) is False
    # Second overlapping occupancy fills cap=2
    busy[50].append(
        BusySlotFact(
            shift_id=2,
            day=1,
            lesson=3,
            interval=(time(9, 10), time(9, 55)),
            classroom_id=50,
        )
    )
    assert classroom_at_capacity(slot, 50, busy, capacity=2) is True
