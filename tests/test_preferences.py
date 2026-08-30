"""Preference slider → CP-SAT scale mapping (no DB)."""
from types import SimpleNamespace

from app.domain.preferences import (
    SOFT_STAGE_COSMETICS,
    SOFT_STAGE_EARLY_ROOMS,
    SOFT_STAGE_PACK_GAPS,
    PreferenceWeights,
    cumulative_soft_stages,
    hardest_first_unit_order,
    freeze_policy,
    solver_scales,
)


def test_adjacent_pairs_slider_zero_ignores_packing():
    scales = solver_scales(PreferenceWeights(adjacent_pairs=0))
    assert scales.hard_adjacent_pairs is False
    assert scales.extra_singleton == 0


def test_adjacent_pairs_slider_mid_is_soft():
    scales = solver_scales(PreferenceWeights(adjacent_pairs=5))
    assert scales.hard_adjacent_pairs is False
    assert scales.extra_singleton == 150


def test_adjacent_pairs_slider_max_is_hard():
    scales = solver_scales(PreferenceWeights(adjacent_pairs=10))
    assert scales.hard_adjacent_pairs is True
    assert scales.extra_singleton == 0


def test_adjacent_pairs_slider_grows_between_one_and_nine():
    low = solver_scales(PreferenceWeights(adjacent_pairs=1))
    high = solver_scales(PreferenceWeights(adjacent_pairs=9))
    assert low.hard_adjacent_pairs is False
    assert high.hard_adjacent_pairs is False
    assert low.extra_singleton < high.extra_singleton


def test_freeze_policy_zero_adjacent_disables():
    policy = freeze_policy(PreferenceWeights(adjacent_pairs=0, hard_subjects_early=10))
    assert policy.enabled is False


def test_freeze_policy_low_adjacent_is_hint():
    policy = freeze_policy(PreferenceWeights(adjacent_pairs=3, hard_subjects_early=5))
    assert policy.enabled is True
    assert policy.hard is False
    assert policy.max_pair_lesson == 5


def test_freeze_policy_default_is_hard_cap_five():
    policy = freeze_policy(PreferenceWeights())
    assert policy.enabled is True
    assert policy.hard is True
    assert policy.max_pair_lesson == 5
    assert policy.min_hours == 4


def test_freeze_policy_max_adjacent_disables_freeze():
    policy = freeze_policy(PreferenceWeights(adjacent_pairs=10, hard_subjects_early=10))
    assert policy.enabled is False


def test_freeze_policy_early_slider_tightens_cap():
    from app.domain.preferences import FREEZE_UNCAP_LESSON

    loose = freeze_policy(PreferenceWeights(adjacent_pairs=5, hard_subjects_early=0))
    tight = freeze_policy(PreferenceWeights(adjacent_pairs=5, hard_subjects_early=10))
    assert loose.max_pair_lesson == FREEZE_UNCAP_LESSON
    assert tight.max_pair_lesson == 3


def test_cumulative_soft_stages_skips_empty_and_accumulates():
    packages = {
        SOFT_STAGE_PACK_GAPS: ["a"],
        SOFT_STAGE_EARLY_ROOMS: [],
        SOFT_STAGE_COSMETICS: ["c"],
    }
    stages = cumulative_soft_stages(packages)
    assert [name for name, _ in stages] == [
        SOFT_STAGE_PACK_GAPS,
        SOFT_STAGE_COSMETICS,
    ]
    assert stages[0][1] == ["a"]
    assert stages[1][1] == ["a", "c"]


def test_hardest_first_unit_order_slots_then_rooms_then_load():
    units = [
        (0, SimpleNamespace(teacher_id=1)),
        (1, SimpleNamespace(teacher_id=2)),
        (2, SimpleNamespace(teacher_id=2)),
        (3, SimpleNamespace(teacher_id=3)),
    ]
    order = hardest_first_unit_order(
        units,
        n_feasible_slots={0: 8, 1: 3, 2: 3, 3: 3},
        scarce_unit_ids={2},
        teacher_load={1: 1, 2: 2, 3: 9},
    )
    assert order[0] == 2
    assert order[1] == 3
    assert order[2] == 1
    assert order[3] == 0


def test_hardest_first_more_hours_before_fewer():
    units = [
        (0, SimpleNamespace(teacher_id=1, assignment_id=10)),
        (1, SimpleNamespace(teacher_id=1, assignment_id=20)),
    ]
    kwargs = dict(
        n_feasible_slots={0: 5, 1: 5},
        scarce_unit_ids=set(),
        teacher_load={1: 2},
        hours_by_assignment={10: 6, 20: 1},
    )
    more = hardest_first_unit_order(units, hours_first="more", **kwargs)
    fewer = hardest_first_unit_order(units, hours_first="fewer", **kwargs)
    assert more == [0, 1]
    assert fewer == [1, 0]


def test_normalize_hours_first_defaults_to_more():
    from app.domain.preferences import HOURS_FIRST_MORE, normalize_hours_first

    assert normalize_hours_first(None) == HOURS_FIRST_MORE
    assert normalize_hours_first("nope") == HOURS_FIRST_MORE
    assert normalize_hours_first("fewer") == "fewer"
