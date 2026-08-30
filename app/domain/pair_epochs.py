"""Pick consecutive same-assignment doubles to freeze between CP-SAT epochs."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field


# Later lesson of a frozen pair must be <= this (5–6 stays free for hard-subjects-early).
MAX_PAIR_LESSON = 5
# Doubles of assignments below this weekly load are not pinned (PE 2h vs math 5–8).
HEAVY_ASSIGNMENT_HOURS = 4


@dataclass
class PairFreezeSpec:
    """Decision vars and units needed to freeze early doubles between epochs."""

    x: dict
    unit_list: list
    feasible_slots_by_unit: dict
    paired_assignment_ids: tuple[tuple[int, int], ...] = ()
    already_frozen: set[tuple[int, str]] = field(default_factory=set)
    hard: bool = True
    max_pair_lesson: int = MAX_PAIR_LESSON
    hours_by_assignment: dict[int, int] = field(default_factory=dict)
    min_hours: int = 1


def freeze_keys_for_good_doubles(
    chosen: dict[int, tuple[int, int, str]],
    assignment_id_by_ui: dict[int, int],
    *,
    max_pair_lesson: int = MAX_PAIR_LESSON,
    paired_assignment_ids: tuple[tuple[int, int], ...] | list[tuple[int, int]] | None = None,
    hours_by_assignment: dict[int, int] | None = None,
    min_hours: int = 1,
) -> list[tuple[int, str]]:
    """Return (unit_index, slot_id) for early adjacent doubles to keep.

    A double is two hours of the same assignment on one day on consecutive
    lessons. The later lesson must be <= ``max_pair_lesson`` so 5–6 is left
    free for a later epoch. Singles are never frozen. Assignments with weekly
    hours below ``min_hours`` are skipped so 2h PE is not pinned before 6h math.

    Subgroup assignment pairs are frozen together: if one group cannot keep
    the same (day, lessons), that double is left unfrozen for both.
    """
    by_asg_day: dict[tuple[int, int], list[tuple[int, int, str]]] = defaultdict(list)
    for ui, (day, lesson, slot_id) in chosen.items():
        aid = assignment_id_by_ui.get(ui)
        if aid is None:
            continue
        by_asg_day[(aid, int(day))].append((ui, int(lesson), slot_id))

    keys: list[tuple[int, str]] = []
    for items in by_asg_day.values():
        items.sort(key=lambda t: t[1])
        used: set[int] = set()
        for i, (ui_a, les_a, sid_a) in enumerate(items):
            if i in used:
                continue
            for j in range(i + 1, len(items)):
                if j in used:
                    continue
                ui_b, les_b, sid_b = items[j]
                if les_b != les_a + 1:
                    continue
                if les_b > max_pair_lesson:
                    continue
                keys.append((ui_a, sid_a))
                keys.append((ui_b, sid_b))
                used.add(i)
                used.add(j)
                break

    if paired_assignment_ids:
        keys = _align_subgroup_freezes(
            keys, chosen, assignment_id_by_ui, tuple(paired_assignment_ids)
        )
    if hours_by_assignment is not None and min_hours > 1:
        keys = [
            (ui, sid)
            for ui, sid in keys
            if int(hours_by_assignment.get(assignment_id_by_ui.get(ui), 0))
            >= min_hours
        ]
    return keys


def _align_subgroup_freezes(
    keys: list[tuple[int, str]],
    chosen: dict[int, tuple[int, int, str]],
    assignment_id_by_ui: dict[int, int],
    paired: tuple[tuple[int, int], ...],
) -> list[tuple[int, str]]:
    freeze_set = set(keys)
    uis_by_aid: dict[int, list[int]] = defaultdict(list)
    for ui in chosen:
        aid = assignment_id_by_ui.get(ui)
        if aid is not None:
            uis_by_aid[aid].append(ui)

    def lessons_on(aid: int, day: int, *, frozen_only: bool) -> set[int]:
        out: set[int] = set()
        for ui in uis_by_aid.get(aid, []):
            d, lesson, sid = chosen[ui]
            if d != day:
                continue
            if frozen_only and (ui, sid) not in freeze_set:
                continue
            out.add(lesson)
        return out

    for a1, a2 in paired:
        days = {
            chosen[ui][0]
            for ui in uis_by_aid.get(a1, []) + uis_by_aid.get(a2, [])
        }
        for day in days:
            union = lessons_on(a1, day, frozen_only=True) | lessons_on(
                a2, day, frozen_only=True
            )
            if not union:
                continue
            c1 = lessons_on(a1, day, frozen_only=False)
            c2 = lessons_on(a2, day, frozen_only=False)
            if not union <= c1 or not union <= c2:
                for ui in uis_by_aid.get(a1, []) + uis_by_aid.get(a2, []):
                    d, _lesson, sid = chosen[ui]
                    if d == day:
                        freeze_set.discard((ui, sid))
                continue
            for ui in uis_by_aid.get(a1, []) + uis_by_aid.get(a2, []):
                d, lesson, sid = chosen[ui]
                if d == day and lesson in union:
                    freeze_set.add((ui, sid))
    return list(freeze_set)
