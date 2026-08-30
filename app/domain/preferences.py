"""Soft preference weights for the CP-SAT objective (no Session)."""
from __future__ import annotations

from dataclasses import dataclass

from app.domain.pair_epochs import HEAVY_ASSIGNMENT_HOURS

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
    extra_singleton: int
    hard_adjacent_pairs: bool
    subgroup_spread: int
    teacher_days: int
    late_lesson: int
    room_placement: int


# Later-lesson cap that does not exclude 5–6 (or later) doubles.
FREEZE_UNCAP_LESSON = 99


@dataclass(frozen=True)
class PairFreezePolicy:
    """How LNS pair-freeze follows the adjacent-pairs / early sliders."""

    enabled: bool
    hard: bool
    max_pair_lesson: int
    min_hours: int = HEAVY_ASSIGNMENT_HOURS


def _max_pair_lesson_from_early(n_early: int) -> int:
    """Higher 'hard subjects early' → freeze only earlier doubles."""
    if n_early <= 0:
        return FREEZE_UNCAP_LESSON
    if n_early <= 4:
        return 6
    if n_early <= 7:
        return 5
    if n_early <= 9:
        return 4
    return 3


def freeze_policy(prefs: PreferenceWeights) -> PairFreezePolicy:
    """Map sliders onto pair-freeze: off / hint / hard, and lesson cap.

    Adjacent-pairs: 0 off; 1–4 hint only; 5–9 hard freeze of early doubles;
    10 off (hard packing already enforces 2+2+…).
    Hard-subjects-early: 0 no cap; 5 → later lesson ≤ 5;
    10 → later lesson ≤ 3 (only 1–2 / 2–3).
    """
    n_pairs = clamp_weight(prefs.adjacent_pairs)
    n_early = clamp_weight(prefs.hard_subjects_early)
    if n_pairs <= 0 or n_pairs >= WEIGHT_MAX:
        return PairFreezePolicy(
            enabled=False, hard=False, max_pair_lesson=5, min_hours=HEAVY_ASSIGNMENT_HOURS
        )
    hard = n_pairs >= 5
    max_lesson = _max_pair_lesson_from_early(n_early)
    min_hours = HEAVY_ASSIGNMENT_HOURS
    return PairFreezePolicy(
        enabled=True,
        hard=hard,
        max_pair_lesson=max_lesson,
        min_hours=min_hours,
    )


SOFT_STAGE_PACK_GAPS = "pack_gaps"
SOFT_STAGE_EARLY_ROOMS = "early_rooms"
SOFT_STAGE_COSMETICS = "cosmetics"

SOFT_STAGE_ORDER = (
    SOFT_STAGE_PACK_GAPS,
    SOFT_STAGE_EARLY_ROOMS,
    SOFT_STAGE_COSMETICS,
)

SOFT_STAGE_TIME_WEIGHT = {
    SOFT_STAGE_PACK_GAPS: 4,
    SOFT_STAGE_EARLY_ROOMS: 2,
    SOFT_STAGE_COSMETICS: 1,
}

# After named packages, this fraction of leftover post-feas time is a Minimize tail.
SOFT_STAGE_TAIL_FRACTION = 0.10

SOFT_STAGE_LABELS = {
    SOFT_STAGE_PACK_GAPS: "окна учителей и сдвоенные",
    SOFT_STAGE_EARLY_ROOMS: "ранние уроки и кабинеты",
    SOFT_STAGE_COSMETICS: "баланс дней и стабильность кабинетов",
}


def empty_soft_packages() -> dict[str, list]:
    return {name: [] for name in SOFT_STAGE_ORDER}


def cumulative_soft_stages(packages: dict[str, list]) -> list[tuple[str, list]]:
    """Non-empty packages in order; each stage's terms include all previous."""
    acc: list = []
    stages: list[tuple[str, list]] = []
    for name in SOFT_STAGE_ORDER:
        extra = list(packages.get(name) or [])
        if not extra:
            continue
        acc = acc + extra
        stages.append((name, acc))
    return stages


HOURS_FIRST_MORE = "more"
HOURS_FIRST_FEWER = "fewer"


def normalize_hours_first(value: str | None) -> str:
    if value == HOURS_FIRST_FEWER:
        return HOURS_FIRST_FEWER
    return HOURS_FIRST_MORE


def hardest_first_unit_order(
    unit_list: list[tuple[int, object]],
    *,
    n_feasible_slots: dict[int, int],
    scarce_unit_ids: set[int],
    teacher_load: dict[int, int],
    hours_by_assignment: dict[int, int] | None = None,
    hours_first: str = HOURS_FIRST_MORE,
) -> list[int]:
    """Unit indices: fewest slots, scarce rooms, weekly hours, busy teachers.

    ``hours_first`` is ``more`` (large assignments first) or ``fewer``.
    """
    hours_map = hours_by_assignment or {}
    more_first = normalize_hours_first(hours_first) == HOURS_FIRST_MORE

    def key(item: tuple[int, object]) -> tuple[int, int, int, int, int, int]:
        ui, unit = item
        tid = getattr(unit, "teacher_id", None)
        load = int(teacher_load.get(tid, 0)) if tid else 0
        aid = getattr(unit, "assignment_id", None)
        hours = int(hours_map.get(aid, 0)) if aid is not None else 0
        hours_rank = -hours if more_first else hours
        return (
            int(n_feasible_slots.get(ui, 10**9)),
            0 if ui in scarce_unit_ids else 1,
            hours_rank,
            -load,
            int(aid) if aid is not None else ui,
            ui,
        )

    return [ui for ui, _ in sorted(unit_list, key=key)]


def solver_scales(prefs: PreferenceWeights) -> SolverScales:
    """Map UI sliders onto existing CP-SAT objective coefficients.

    Adjacent-pairs slider controls weekly packing density only: 0 — singles
    allowed; 1–9 — growing penalty for extra singleton days; 10 — hard
    packing (even hours all doubles, odd hours one leftover single).
    Same-day doubles are always consecutive when max-per-day is 2.
    """
    f_early = prefs.factor("hard_subjects_early")
    n_pairs = clamp_weight(prefs.adjacent_pairs)
    hard_pairs = n_pairs >= WEIGHT_MAX
    f_pairs = n_pairs / float(WEIGHT_DEFAULT)
    f_gaps = prefs.factor("teacher_gaps")
    f_stab = prefs.factor("classroom_stability")
    soft_pairs = n_pairs > 0 and not hard_pairs
    return SolverScales(
        slot=max(1, int(round(1 * f_early))),
        day_balance=max(1, int(round(1 * f_stab))),
        extra_singleton=max(1, int(round(150 * f_pairs))) if soft_pairs else 0,
        hard_adjacent_pairs=hard_pairs,
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
