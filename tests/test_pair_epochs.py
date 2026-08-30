"""Pick early adjacent doubles to freeze between CP-SAT epochs."""
from app.domain.pair_epochs import freeze_keys_for_good_doubles


def test_early_adjacent_pair_is_frozen():
    chosen = {0: (1, 1, "s1"), 1: (1, 2, "s2")}
    keys = freeze_keys_for_good_doubles(chosen, {0: 10, 1: 10})
    assert set(keys) == {(0, "s1"), (1, "s2")}


def test_pair_4_5_is_frozen():
    chosen = {0: (1, 4, "a"), 1: (1, 5, "b")}
    keys = freeze_keys_for_good_doubles(chosen, {0: 1, 1: 1})
    assert set(keys) == {(0, "a"), (1, "b")}


def test_late_pair_5_6_not_frozen():
    chosen = {0: (1, 5, "a"), 1: (1, 6, "b")}
    keys = freeze_keys_for_good_doubles(chosen, {0: 1, 1: 1})
    assert keys == []


def test_late_pair_5_6_frozen_when_uncapped():
    chosen = {0: (1, 5, "a"), 1: (1, 6, "b")}
    keys = freeze_keys_for_good_doubles(chosen, {0: 1, 1: 1}, max_pair_lesson=99)
    assert set(keys) == {(0, "a"), (1, "b")}


def test_strict_early_cap_skips_4_5():
    chosen = {0: (1, 4, "a"), 1: (1, 5, "b")}
    keys = freeze_keys_for_good_doubles(chosen, {0: 1, 1: 1}, max_pair_lesson=3)
    assert keys == []
    chosen_early = {0: (1, 1, "a"), 1: (1, 2, "b")}
    keys_early = freeze_keys_for_good_doubles(
        chosen_early, {0: 1, 1: 1}, max_pair_lesson=3
    )
    assert set(keys_early) == {(0, "a"), (1, "b")}


def test_singleton_not_frozen():
    chosen = {0: (1, 1, "a")}
    assert freeze_keys_for_good_doubles(chosen, {0: 1}) == []


def test_light_2h_double_skipped_when_min_hours_is_heavy():
    chosen = {0: (1, 1, "pe1"), 1: (1, 2, "pe2")}
    keys = freeze_keys_for_good_doubles(
        chosen,
        {0: 2, 1: 2},
        hours_by_assignment={2: 2},
        min_hours=4,
    )
    assert keys == []


def test_6h_double_frozen_when_min_hours_is_heavy():
    chosen = {0: (1, 1, "m1"), 1: (1, 2, "m2")}
    keys = freeze_keys_for_good_doubles(
        chosen,
        {0: 10, 1: 10},
        hours_by_assignment={10: 6},
        min_hours=4,
    )
    assert set(keys) == {(0, "m1"), (1, "m2")}


def test_three_hours_freezes_first_double_leaves_single():
    chosen = {0: (1, 1, "a"), 1: (1, 2, "b"), 2: (1, 3, "c")}
    keys = freeze_keys_for_good_doubles(chosen, {0: 1, 1: 1, 2: 1})
    assert set(keys) == {(0, "a"), (1, "b")}


def test_different_assignments_not_paired():
    chosen = {0: (1, 1, "a"), 1: (1, 2, "b")}
    keys = freeze_keys_for_good_doubles(chosen, {0: 1, 1: 2})
    assert keys == []


def test_non_consecutive_not_frozen():
    chosen = {0: (1, 1, "a"), 1: (1, 3, "b")}
    keys = freeze_keys_for_good_doubles(chosen, {0: 1, 1: 1})
    assert keys == []


def test_subgroup_pair_frozen_together():
    chosen = {
        0: (1, 1, "g1a"),
        1: (1, 2, "g1b"),
        2: (1, 1, "g2a"),
        3: (1, 2, "g2b"),
    }
    keys = freeze_keys_for_good_doubles(
        chosen,
        {0: 10, 1: 10, 2: 11, 3: 11},
        paired_assignment_ids=((10, 11),),
    )
    assert set(keys) == {(0, "g1a"), (1, "g1b"), (2, "g2a"), (3, "g2b")}


def test_subgroup_mismatch_drops_both():
    """Group 1 has 1–2; group 2 is on 5–6 — freeze neither."""
    chosen = {
        0: (1, 1, "g1a"),
        1: (1, 2, "g1b"),
        2: (1, 5, "g2a"),
        3: (1, 6, "g2b"),
    }
    keys = freeze_keys_for_good_doubles(
        chosen,
        {0: 10, 1: 10, 2: 11, 3: 11},
        paired_assignment_ids=((10, 11),),
    )
    assert keys == []
