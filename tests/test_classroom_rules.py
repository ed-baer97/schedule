"""Unit tests for classroom suitability and placement cost (no DB)."""
from app.domain.classroom_rules import (
    COST_GENERAL,
    COST_OTHER_SUBJECT,
    COST_OWNER_SUBJECT,
    COST_SAME_SUBJECT,
    ClassroomFact,
    PlacementContext,
    candidate_rooms_for,
    placement_cost,
    rank_candidate_rooms,
    room_allows,
    room_allows_subject,
    room_denial_message,
)


MATH = 1
INFO = 2
RUSSIAN = 3


def _room(
    rid: int,
    subject_id: int | None = None,
    exclusive: bool = False,
    school_level: str | None = None,
    subgroup_only: bool = False,
) -> ClassroomFact:
    return ClassroomFact(
        id=rid,
        subject_ids=frozenset() if subject_id is None else frozenset({subject_id}),
        is_exclusive=exclusive,
        classes_capacity=1,
        school_level=school_level,
        subgroup_only=subgroup_only,
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


def test_force_teacher_home_returns_only_home_room():
    home = _room(10)
    other = _room(43, MATH)
    ctx = PlacementContext(
        subject_id=RUSSIAN,
        requires_fixed_classroom=False,
        teacher_home_classroom_id=10,
        force_teacher_home=True,
    )
    assert candidate_rooms_for([home, other], ctx) == [(10, COST_OWNER_SUBJECT)]


def test_force_teacher_home_falls_through_if_home_missing():
    other = _room(43, MATH)
    ctx = PlacementContext(
        subject_id=MATH,
        requires_fixed_classroom=False,
        teacher_home_classroom_id=10,
        force_teacher_home=True,
    )
    ranked = candidate_rooms_for([other], ctx)
    assert ranked == [(43, COST_SAME_SUBJECT)]


def test_force_teacher_home_skips_exclusive_foreign_home():
    lab = _room(32, INFO, exclusive=True)
    math_room = _room(43, MATH)
    ctx = PlacementContext(
        subject_id=MATH,
        requires_fixed_classroom=False,
        teacher_home_classroom_id=32,
        force_teacher_home=True,
    )
    ranked = candidate_rooms_for([lab, math_room], ctx)
    assert ranked[0] == (43, COST_SAME_SUBJECT)
    assert 32 not in {rid for rid, _ in ranked}


def test_force_teacher_home_ignored_for_fixed_subject():
    lab = _room(32, INFO, exclusive=True)
    home = _room(10)
    ctx = PlacementContext(
        subject_id=INFO,
        requires_fixed_classroom=True,
        teacher_home_classroom_id=10,
        force_teacher_home=True,
    )
    ranked = candidate_rooms_for([lab, home], ctx)
    assert ranked == [(32, COST_SAME_SUBJECT)]


def test_exclusive_room_allows_any_tagged_subject():
    cluster = ClassroomFact(
        id=12,
        subject_ids=frozenset({MATH, 4, 5}),
        is_exclusive=True,
        classes_capacity=1,
    )
    assert room_allows_subject(cluster, subject_id=MATH, requires_fixed_classroom=False)
    assert room_allows_subject(cluster, subject_id=4, requires_fixed_classroom=False)
    assert room_allows_subject(cluster, subject_id=5, requires_fixed_classroom=False)
    assert not room_allows_subject(
        cluster, subject_id=RUSSIAN, requires_fixed_classroom=False
    )


def test_multi_subject_room_same_subject_cost():
    room = ClassroomFact(
        id=43,
        subject_ids=frozenset({MATH, 4, 5}),
        is_exclusive=False,
        classes_capacity=1,
    )
    ctx_math = PlacementContext(subject_id=MATH, requires_fixed_classroom=False)
    ctx_ru = PlacementContext(subject_id=RUSSIAN, requires_fixed_classroom=False)
    assert placement_cost(room, ctx_math) == COST_SAME_SUBJECT
    assert placement_cost(room, ctx_ru) == COST_OTHER_SUBJECT


def test_secondary_blocked_from_elementary_room():
    home = _room(11, school_level="elementary")
    gym = _room(1)
    ctx = PlacementContext(
        subject_id=MATH,
        requires_fixed_classroom=False,
        class_school_level="secondary",
    )
    assert room_allows(
        home,
        subject_id=MATH,
        requires_fixed_classroom=False,
        class_school_level="secondary",
    ) is False
    assert room_allows(
        gym,
        subject_id=MATH,
        requires_fixed_classroom=False,
        class_school_level="secondary",
    )
    ranked = rank_candidate_rooms([home, gym], ctx)
    assert ranked == [(1, COST_GENERAL)]
    msg = room_denial_message(
        home,
        subject_id=MATH,
        subject_name="Математика",
        requires_fixed_classroom=False,
        room_display_name="11",
        class_school_level="secondary",
    )
    assert msg is not None and "начальной" in msg


def test_force_class_home_returns_only_class_room():
    home = _room(11, school_level="elementary")
    other = _room(43, MATH)
    gym = _room(1)
    ctx = PlacementContext(
        subject_id=RUSSIAN,
        requires_fixed_classroom=False,
        class_home_classroom_id=11,
        class_school_level="elementary",
        force_class_home=True,
    )
    assert candidate_rooms_for([home, other, gym], ctx) == [(11, COST_OWNER_SUBJECT)]


def test_force_class_home_ignored_for_fixed_subject():
    home = _room(11, school_level="elementary")
    lab = _room(32, INFO, exclusive=True)
    ctx = PlacementContext(
        subject_id=INFO,
        requires_fixed_classroom=True,
        class_home_classroom_id=11,
        class_school_level="elementary",
        force_class_home=True,
    )
    ranked = candidate_rooms_for([home, lab], ctx)
    assert ranked == [(32, COST_SAME_SUBJECT)]


def test_force_teacher_home_wins_over_force_class_home():
    class_home = _room(11, school_level="elementary")
    teacher_home = _room(20)
    ctx = PlacementContext(
        subject_id=RUSSIAN,
        requires_fixed_classroom=False,
        teacher_home_classroom_id=20,
        class_home_classroom_id=11,
        class_school_level="elementary",
        force_teacher_home=True,
        force_class_home=True,
    )
    assert candidate_rooms_for([class_home, teacher_home], ctx) == [
        (20, COST_OWNER_SUBJECT)
    ]


def test_subgroup_only_room_blocks_whole_class():
    small = _room(5, subgroup_only=True)
    gym = _room(1)
    whole = PlacementContext(
        subject_id=MATH,
        requires_fixed_classroom=False,
        class_school_level="secondary",
        is_subgroup=False,
    )
    assert (
        room_allows(
            small,
            subject_id=MATH,
            requires_fixed_classroom=False,
            class_school_level="secondary",
            is_subgroup=False,
        )
        is False
    )
    assert room_allows(
        gym,
        subject_id=MATH,
        requires_fixed_classroom=False,
        class_school_level="secondary",
        is_subgroup=False,
    )
    ranked = rank_candidate_rooms([small, gym], whole)
    assert ranked == [(1, COST_GENERAL)]
    msg = room_denial_message(
        small,
        subject_id=MATH,
        subject_name="Математика",
        requires_fixed_classroom=False,
        room_display_name="5",
        is_subgroup=False,
    )
    assert msg is not None and "подгрупп" in msg


def test_subgroup_only_room_allows_subgroup():
    small = _room(5, subgroup_only=True)
    ctx = PlacementContext(
        subject_id=MATH,
        requires_fixed_classroom=False,
        class_school_level="secondary",
        is_subgroup=True,
    )
    assert room_allows(
        small,
        subject_id=MATH,
        requires_fixed_classroom=False,
        class_school_level="secondary",
        is_subgroup=True,
    )
    ranked = candidate_rooms_for([small], ctx)
    assert ranked == [(5, COST_GENERAL)]

