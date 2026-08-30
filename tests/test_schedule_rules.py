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


def test_slot_facts_conflict_same_bells_different_days():
    """Clock-only bells must not make Monday occupy Tuesday."""
    a = SlotFact(
        slot_id="c1:d2:l1",
        class_id=1,
        day=2,
        lesson=1,
        shift_id=1,
        interval=(time(8, 0), time(8, 45)),
    )
    b = BusySlotFact(
        shift_id=1,
        day=1,
        lesson=1,
        interval=(time(8, 0), time(8, 45)),
    )
    assert slot_facts_conflict(a, b) is False


def test_teacher_busy_at_slot_same_bells_different_day():
    slot = SlotFact(
        slot_id="c1:d2:l1",
        class_id=1,
        day=2,
        lesson=1,
        shift_id=1,
        interval=(time(8, 0), time(8, 45)),
    )
    busy = {
        10: [
            BusySlotFact(
                shift_id=1,
                day=1,
                lesson=1,
                interval=(time(8, 0), time(8, 45)),
            )
        ],
    }
    assert teacher_busy_at_slot(slot, 10, busy) is False


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


def test_secondary_grade_bands_split_5_6_then_7_9():
    from types import SimpleNamespace

    from app.domain.school_class import (
        grade_bands_for_level,
        partition_classes_by_grade_bands,
    )

    bands = grade_bands_for_level("secondary")
    assert bands[0].label == "5–6 классы"
    assert bands[0].contains(5) and bands[0].contains(6)
    assert not bands[0].contains(7)
    assert bands[1].contains(7) and bands[1].contains(9)
    classes = [
        SimpleNamespace(id=1, grade=5),
        SimpleNamespace(id=2, grade=6),
        SimpleNamespace(id=3, grade=8),
        SimpleNamespace(id=4, grade=10),
    ]
    parts = partition_classes_by_grade_bands(classes, "secondary")
    assert [p[0].label for p in parts] == ["5–6 классы", "7–9 классы"]
    assert [c.grade for c in parts[0][1]] == [5, 6]
    assert [c.grade for c in parts[1][1]] == [8, 10]


def test_elementary_grade_bands_1_2_then_3_4():
    from types import SimpleNamespace

    from app.domain.school_class import partition_classes_by_grade_bands

    classes = [
        SimpleNamespace(grade=1),
        SimpleNamespace(grade=4),
    ]
    parts = partition_classes_by_grade_bands(classes, "elementary")
    assert [p[0].label for p in parts] == ["1–2 классы", "3–4 классы"]


def test_leftover_singles_and_extra_singleton_days():
    from app.domain.schedule_rules import extra_singleton_days, leftover_singles_allowed

    assert leftover_singles_allowed(6) == 0
    assert leftover_singles_allowed(5) == 1
    assert leftover_singles_allowed(1) == 1
    assert extra_singleton_days(0, 6) == 0
    assert extra_singleton_days(4, 6) == 4
    assert extra_singleton_days(1, 5) == 0
    assert extra_singleton_days(3, 5) == 2


def test_second_hour_is_split():
    from app.domain.schedule_rules import second_hour_is_split

    assert second_hour_is_split([], 5) is False
    assert second_hour_is_split([5], 6) is False
    assert second_hour_is_split([5], 4) is False
    assert second_hour_is_split([5], 7) is True
    assert second_hour_is_split([5, 6], 7) is False
