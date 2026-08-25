"""Soft preference weights for the CP-SAT objective (no Session)."""
from __future__ import annotations

from dataclasses import dataclass

WEIGHT_MIN = 0
WEIGHT_MAX = 10
WEIGHT_DEFAULT = 5


def clamp_weight(value: int | None, default: int = WEIGHT_DEFAULT) -> int:
    if value is None:
        return default
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(WEIGHT_MIN, min(WEIGHT_MAX, n))


@dataclass(frozen=True)
class PreferenceWeights:
    teacher_gaps: int = WEIGHT_DEFAULT
    hard_subjects_early: int = WEIGHT_DEFAULT
    adjacent_pairs: int = WEIGHT_DEFAULT
    classroom_stability: int = WEIGHT_DEFAULT

    def factor(self, field: str) -> float:
        """0..10 slider → multiplier around 1.0 at the default (5)."""
        raw = getattr(self, field, WEIGHT_DEFAULT)
        return clamp_weight(raw) / float(WEIGHT_DEFAULT)


@dataclass(frozen=True)
class SolverScales:
    slot: int
    day_balance: int
    non_adjacent_pair: int
    subgroup_spread: int
    teacher_days: int
    late_lesson: int
    room_placement: int


def solver_scales(prefs: PreferenceWeights) -> SolverScales:
    """Map UI sliders onto existing CP-SAT objective coefficients."""
    f_early = prefs.factor("hard_subjects_early")
    f_pairs = prefs.factor("adjacent_pairs")
    f_gaps = prefs.factor("teacher_gaps")
    f_stab = prefs.factor("classroom_stability")
    return SolverScales(
        slot=max(1, int(round(1 * f_early))),
        day_balance=max(1, int(round(1 * f_stab))),
        non_adjacent_pair=max(0, int(round(200 * f_pairs))),
        subgroup_spread=max(0, int(round(30 * f_stab))),
        teacher_days=max(0, int(round(40 * f_gaps))),
        late_lesson=max(0, int(round(25 * f_early))),
        room_placement=max(1, int(round(2 * f_stab))),
    )


def weights_from_settings(settings, overrides: dict | None = None) -> PreferenceWeights:
    o = overrides or {}

    def pick(key: str) -> int:
        if key in o and o[key] is not None:
            return clamp_weight(o[key])
        if settings is None:
            return WEIGHT_DEFAULT
        return clamp_weight(getattr(settings, key, WEIGHT_DEFAULT))

    return PreferenceWeights(
        teacher_gaps=pick("pref_teacher_gaps"),
        hard_subjects_early=pick("pref_hard_subjects_early"),
        adjacent_pairs=pick("pref_adjacent_pairs"),
        classroom_stability=pick("pref_classroom_stability"),
    )
