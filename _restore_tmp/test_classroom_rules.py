"""Unit tests for classroom suitability and placement cost (no DB)."""
from app.domain.classroom_rules import (
    COST_GENERAL,
    COST_OTHER_SUBJECT,
    COST_OWNER_SUBJECT,
    COST_SAME_SUBJECT,
    ClassroomFact,
    PlacementContext,
    placement_cost,
    rank_candidate_rooms,
    room_allows_subject,
)


MATH = 1
INFO = 2
RUSSIAN = 3


def _room(rid: int, subject_id: int | None = None, exclusive: bool = False) -> ClassroomFact:
    return ClassroomFact(
        id=rid,
        subject_id=subject_id,
        is_exclusive=exclusive,
        classes_capacity=1,
    )


def test_fixed_subject_only_own_pool():
    lab = _room(32, INFO, exclusive=True)
    math_room = _room(43, MATH, exclusive=False)
    assert room_allows_subject(lab, subject_id=INFO, requires_fixed_classroom=True)
    assert not room_allows_subject(
        math_room, subject_id=INFO, requires_fixed_classroom=True
    )
    assert not room_allows_subject(
        _room(101), subject_id=INFO, requires_fixed_classroom=True
    )


def test_exclusive_room_blocks_other_subjects():
    lab = _room(32, INFO, exclusive=True)
    assert not room_allows_subject(
        lab, subject_id=MATH, requires_fixed_classroom=False
    )
    assert room_allows_subject(lab, subject_id=INFO, requires_fixed_classroom=False)


def test_non_exclusive_subject_room_accepts_other_non_fixed():
    math43 = _room(43, MATH, exclusive=False)
    assert room_allows_subject(
        math43, subject_id=MATH, requires_fixed_classroom=False
    )
    assert room_allows_subject(
        math43, subject_id=RUSSIAN, requires_fixed_classroom=False
    )
    assert not room_allows_subject(
        math43, subject_id=INFO, requires_fixed_classroom=True
    )


def test_owner_math_priority():
    room43 = _room(43, MATH, exclusive=False)
    room44 = _room(44, MATH, exclusive=False)
    general = _room(101)
    other = _room(55, RUSSIAN, exclusive=False)
    ctx = PlacementContext(
        subject_id=MATH,
        requires_fixed_classroom=False,
        teacher_home_classroom_id=43,
        classroom_mode="class_room",
    )
    assert placement_cost(room43, ctx) == COST_OWNER_SUBJECT
    assert placement_cost(room44, ctx) == COST_SAME_SUBJECT
    assert placement_cost(general, ctx) == COST_GENERAL
    assert placement_cost(other, ctx) == COST_OTHER_SUBJECT

    ranked = rank_candidate_rooms([other, general, room44, room43], ctx)
    assert ranked[0] == (43, COST_OWNER_SUBJECT)
    assert ranked[1][0] == 44


def test_russian_in_math_room_allowed_costlier_than_math():
    room43 = _room(43, MATH, exclusive=False)
    ctx_ru = PlacementContext(
        subject_id=RUSSIAN,
        requires_fixed_classroom=False,
        teacher_home_classroom_id=None,
    )
    ctx_math = PlacementContext(
        subject_id=MATH,
        requires_fixed_classroom=False,
        teacher_home_classroom_id=None,
    )
    assert placement_cost(room43, ctx_ru) == COST_OTHER_SUBJECT
    assert placement_cost(room43, ctx_math) == COST_SAME_SUBJECT
