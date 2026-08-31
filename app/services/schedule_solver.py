"""
Graph-based residual solver for schedule auto-fill.
CP-SAT global solver (one shift): hard feasibility, then staged soft packages.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass, field
import threading
import time
from typing import Any, Callable

from app.domain.classroom_rules import MSG_NO_CLASSROOM
from app.domain.pair_epochs import PairFreezeSpec, freeze_keys_for_good_doubles
from app.domain.schedule_facts import BusySlotFact, SlotFact, UnitFact
from app.domain.schedule_rules import (
    classroom_at_capacity,
    leftover_singles_allowed,
    occupancy_blocks_unit,
    second_hour_is_split,
    subject_day_limit_reached,
    teacher_busy_at_slot,
    teacher_class_day_limit_reached,
    units_cannot_share_class_slot,
)
from sqlalchemy.orm import joinedload

from app.config import Config
from app.domain.preferences import (
    SOFT_STAGE_COSMETICS,
    SOFT_STAGE_EARLY_ROOMS,
    SOFT_STAGE_LABELS,
    SOFT_STAGE_PACK_GAPS,
    SOFT_STAGE_TIME_WEIGHT,
    SOFT_STAGE_TAIL_FRACTION,
    empty_soft_packages,
    cumulative_soft_stages,
    freeze_policy,
    hardest_first_unit_order,
    HOURS_FIRST_MORE,
    normalize_hours_first,
    solver_scales,
    weights_from_settings,
)
from app.models import SchoolClass, TeachingAssignment
from app.services.assignment_hours import placed_counts, remaining_for
from app.services.classroom_resolver import (
    candidate_classrooms,
    load_classroom_facts,
    load_settings,
)
from app.services.schedule_fact_loader import (
    build_slots_by_class,
    build_unit_facts,
    load_class_occupancy,
    load_classroom_busy,
    load_external_teacher_busy,
    load_teacher_busy,
)
from app.services.schedule_service import ScheduleService
from app.services.validators import ScheduleValidator

try:
    from ortools.sat.python import cp_model
except ImportError:  # pragma: no cover
    cp_model = None


def _add_capacity_overlap_constraints(model, items: list[tuple[Any, SlotFact]], capacity: int):
    """
    Constrain BoolVars so that at most ``capacity`` selected slots overlap in time.
    Uses interval sweep when bells are present; otherwise same day+lesson.
    Mixed (some missing intervals) follows slot_facts_conflict semantics.
    """
    if not items or capacity < 1:
        return
    by_day: dict[int, list[tuple[Any, SlotFact]]] = defaultdict(list)
    for var, slot in items:
        by_day[slot.day].append((var, slot))

    for day_items in by_day.values():
        with_iv = [(v, s) for v, s in day_items if s.interval is not None]
        without = [(v, s) for v, s in day_items if s.interval is None]

        if with_iv:
            starts = sorted({s.interval[0] for _, s in with_iv})
            for t in starts:
                active = [
                    v
                    for v, s in with_iv
                    if s.interval[0] <= t < s.interval[1]
                ]
                if active:
                    model.Add(sum(active) <= capacity)

        by_lesson: dict[int, list] = defaultdict(list)
        for v, s in without:
            by_lesson[s.lesson].append(v)
        if without:
            for v, s in with_iv:
                if any(s2.lesson == s.lesson for _, s2 in without):
                    by_lesson[s.lesson].append(v)
        for vars_ in by_lesson.values():
            if vars_:
                model.Add(sum(vars_) <= capacity)


def _hint_bool_maps(model, solver, *var_maps: dict) -> None:
    for var_map in var_maps:
        for var in var_map.values():
            try:
                model.AddHint(var, int(solver.Value(var)))
            except Exception:
                continue


def _chosen_unit_slots(solver, x: dict, unit_list, feasible_slots_by_unit: dict) -> dict[int, tuple[int, int, str]]:
    chosen: dict[int, tuple[int, int, str]] = {}
    for ui, _unit in unit_list:
        for slot in feasible_slots_by_unit.get(ui, []):
            var = x.get((ui, slot.slot_id))
            if var is None:
                continue
            try:
                if int(solver.Value(var)) != 1:
                    continue
            except Exception:
                continue
            chosen[ui] = (int(slot.day), int(slot.lesson), slot.slot_id)
            break
    return chosen


def _freeze_good_doubles(model, solver, spec: PairFreezeSpec) -> int:
    """Pin or hint early adjacent doubles from ``solver``; return new var count."""
    chosen = _chosen_unit_slots(solver, spec.x, spec.unit_list, spec.feasible_slots_by_unit)
    assignment_id_by_ui = {ui: unit.assignment_id for ui, unit in spec.unit_list}
    keys = freeze_keys_for_good_doubles(
        chosen,
        assignment_id_by_ui,
        max_pair_lesson=spec.max_pair_lesson,
        paired_assignment_ids=spec.paired_assignment_ids,
        hours_by_assignment=spec.hours_by_assignment or None,
        min_hours=spec.min_hours,
    )
    added = 0
    for ui, slot_id in keys:
        key = (ui, slot_id)
        if key in spec.already_frozen:
            continue
        var = spec.x.get(key)
        if var is None:
            continue
        if spec.hard:
            model.Add(var == 1)
        else:
            model.AddHint(var, 1)
        spec.already_frozen.add(key)
        added += 1
    return added


def _apply_cp_sat_params(
    solver,
    random_seed: int,
    time_limit_sec: float,
    num_workers: int,
    *,
    stop_after_first: bool,
) -> None:
    solver.parameters.max_time_in_seconds = float(time_limit_sec)
    solver.parameters.num_search_workers = int(num_workers)
    solver.parameters.random_seed = int(random_seed)
    if stop_after_first:
        solver.parameters.stop_after_first_solution = True


def _add_hardest_first_decision_strategy(
    model,
    unit_list,
    feasible_slots_by_unit: dict,
    x: dict,
    y: dict,
    *,
    hours_by_assignment: dict[int, int] | None = None,
    hours_first: str = HOURS_FIRST_MORE,
) -> None:
    """Branch on tight units first, then large (or small) weekly assignments."""
    if cp_model is None or not x:
        return
    scarce = {ui for ui, _sid, _rid in y}
    teacher_load: dict[int, int] = defaultdict(int)
    for _ui, unit in unit_list:
        if unit.teacher_id:
            teacher_load[unit.teacher_id] += 1
    n_slots = {ui: len(feasible_slots_by_unit.get(ui, [])) for ui, _ in unit_list}
    ordered_uis = hardest_first_unit_order(
        list(unit_list),
        n_feasible_slots=n_slots,
        scarce_unit_ids=scarce,
        teacher_load=dict(teacher_load),
        hours_by_assignment=hours_by_assignment,
        hours_first=hours_first,
    )
    slots_by_ui = {ui: feasible_slots_by_unit.get(ui, []) for ui, _ in unit_list}
    ordered_vars = []
    for ui in ordered_uis:
        for slot in sorted(slots_by_ui.get(ui, []), key=lambda s: (s.day, s.lesson)):
            var = x.get((ui, slot.slot_id))
            if var is not None:
                ordered_vars.append(var)
    if not ordered_vars:
        return
    model.AddDecisionStrategy(
        ordered_vars,
        cp_model.CHOOSE_FIRST,
        cp_model.SELECT_MAX_VALUE,
    )


def run_staged_cp_sat_search(
    model,
    *,
    hint_maps: tuple[dict, ...],
    soft_stages: list[tuple[str, list]],
    time_limit_sec: float,
    random_seed: int,
    num_workers: int,
    min_remaining_sec: float = 0.5,
    should_stop: Callable[[], bool] | None = None,
    on_progress: Callable[[int, int, str], None] | None = None,
    solve_fn: Callable | None = None,
    pair_freeze: PairFreezeSpec | None = None,
) -> tuple[str | None, Any, Any, float]:
    """Feasibility, named soft packages, then Minimize tail until the time limit.

    Phase 1 has no Minimize — CP-SAT without an objective returns OPTIMAL on
    the first solution, so later stages always run when time remains.
    Named packages share a weighted slice of leftover time minus a tail
    reserve, so the last package cannot consume the whole remainder when it
    proves OPTIMAL in a few seconds. The tail re-Minimizes the last package
    (new seed each round) until remaining time is gone; it stops early only
    if a round is OPTIMAL and freeze adds no new keys (same objective is
    proven). Freeze waits until after pack_gaps so 6h math can pack before
    2h PE is pinned. Frozen x==1 stays on if a later stage times out.
    """

    def _notify(current: int, message: str) -> None:
        if not on_progress:
            return
        try:
            on_progress(current, 100, message)
        except Exception:
            pass

    def _solve(solver) -> Any:
        if solve_fn is not None:
            return solve_fn(solver, model)
        return solver.Solve(model)

    t0 = time.perf_counter()
    budget = max(0.1, float(time_limit_sec))
    _notify(30, f"Ищу допустимое расписание (лимит {int(budget)} с)…")

    solver_feas = cp_model.CpSolver()
    _apply_cp_sat_params(
        solver_feas, random_seed, budget, num_workers, stop_after_first=True
    )
    status_feas = _solve(solver_feas)
    elapsed = time.perf_counter() - t0
    if should_stop and should_stop():
        return "CANCELLED", status_feas, solver_feas, elapsed
    if status_feas not in (cp_model.FEASIBLE, cp_model.OPTIMAL):
        return None, status_feas, solver_feas, elapsed

    best_status, best_solver = status_feas, solver_feas
    optimized = False
    if not soft_stages:
        _notify(80, f"Допустимое расписание найдено за {elapsed:.0f} с")
        return None, best_status, best_solver, elapsed

    _hint_bool_maps(model, best_solver, *hint_maps)
    has_pack_gaps = any(name == SOFT_STAGE_PACK_GAPS for name, _ in soft_stages)
    if pair_freeze is not None and not has_pack_gaps:
        added = _freeze_good_doubles(model, best_solver, pair_freeze)
        if added:
            n_pairs = added // 2
            verb = "Якорю" if pair_freeze.hard else "Подсказываю"
            _notify(45, f"{verb} {n_pairs} тяжёлых сдвоенных, ищу остальное…")
            _hint_bool_maps(model, best_solver, *hint_maps)

    n_stages = len(soft_stages)
    remaining_after_feas = budget - (time.perf_counter() - t0)
    tail_reserve = 0.0
    if remaining_after_feas >= 2.0:
        tail_reserve = remaining_after_feas * SOFT_STAGE_TAIL_FRACTION
        if tail_reserve < min_remaining_sec:
            tail_reserve = 0.0
    named_ceiling = budget - tail_reserve

    for i, (name, terms) in enumerate(soft_stages):
        remaining_named = named_ceiling - (time.perf_counter() - t0)
        if remaining_named < min_remaining_sec:
            break
        leftover_names = [n for n, _ in soft_stages[i:]]
        weight_sum = sum(SOFT_STAGE_TIME_WEIGHT.get(n, 1) for n in leftover_names) or 1
        slice_sec = remaining_named * SOFT_STAGE_TIME_WEIGHT.get(name, 1) / weight_sum
        if slice_sec < min_remaining_sec:
            break

        label = SOFT_STAGE_LABELS.get(name, name)
        pct = 50 + int(25 * i / max(1, n_stages))
        _notify(
            pct,
            f"Допустимое найдено за {elapsed:.0f} с, улучшаю {label} ({slice_sec:.0f} с)…",
        )
        model.ClearObjective()
        model.Minimize(sum(terms))

        solver_i = cp_model.CpSolver()
        _apply_cp_sat_params(
            solver_i, random_seed, slice_sec, num_workers, stop_after_first=False
        )
        status_i = _solve(solver_i)
        elapsed = time.perf_counter() - t0
        if should_stop and should_stop():
            return "CANCELLED", status_i, solver_i, elapsed
        if status_i in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            best_status, best_solver = status_i, solver_i
            optimized = True
            _hint_bool_maps(model, best_solver, *hint_maps)
        if pair_freeze is not None and name == SOFT_STAGE_PACK_GAPS:
            added = _freeze_good_doubles(model, best_solver, pair_freeze)
            if added:
                n_pairs = added // 2
                verb = "Якорю" if pair_freeze.hard else "Подсказываю"
                _notify(
                    58,
                    f"{verb} {n_pairs} тяжёлых сдвоенных, ищу остальное…",
                )
                _hint_bool_maps(model, best_solver, *hint_maps)

    last_terms = soft_stages[-1][1]
    remaining = budget - (time.perf_counter() - t0)
    if remaining >= min_remaining_sec:
        if should_stop and should_stop():
            elapsed = time.perf_counter() - t0
            return "CANCELLED", best_status, best_solver, elapsed

        _notify(72, f"Докручиваю до лимита ({remaining:.0f} с)…")
        model.ClearObjective()
        model.Minimize(sum(last_terms))
        solver_t = cp_model.CpSolver()
        _apply_cp_sat_params(
            solver_t,
            random_seed + 1,
            remaining,
            num_workers,
            stop_after_first=False,
        )
        status_t = _solve(solver_t)
        elapsed = time.perf_counter() - t0
        if should_stop and should_stop():
            return "CANCELLED", status_t, solver_t, elapsed
        if status_t in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            best_status, best_solver = status_t, solver_t
            optimized = True
            _hint_bool_maps(model, best_solver, *hint_maps)

    elapsed = time.perf_counter() - t0
    if not optimized and best_status == cp_model.OPTIMAL:
        best_status = cp_model.FEASIBLE
    if best_status == cp_model.OPTIMAL:
        _notify(80, f"Найдено оптимальное расписание за {elapsed:.0f} с")
    else:
        _notify(80, f"Допустимое расписание найдено за {elapsed:.0f} с")
    return None, best_status, best_solver, elapsed


def _add_assignment_pair_packing(
    model,
    *,
    assignments,
    unit_list,
    feasible_slots_by_unit,
    x,
    shift_obj,
    max_per_subject_day: int,
    scales,
    obj_terms: list,
) -> None:
    """Same-day doubles must be neighbouring lessons; slider packs weekly 2+2+…

    When max-per-day is 2, two hours of a subject on one day cannot sandwich
    another subject (English 5 + Biology 6 + English 7 is infeasible). Slider 10
    additionally forbids extra singleton days; 1–9 penalize them; 0 does not.
    """
    if max_per_subject_day < 2:
        return
    hard_pack = bool(scales.hard_adjacent_pairs)
    w_extra = int(scales.extra_singleton)

    lesson_start = shift_obj.start_lesson
    lesson_end = shift_obj.start_lesson + shift_obj.lessons_count

    for a in assignments:
        hours = int(a.hours_per_week or 0)
        if hours <= 0:
            continue
        uidxs = [ui for ui, u in unit_list if u.assignment_id == a.id]
        if not uidxs:
            continue

        is_one_vars = []
        leftover = leftover_singles_allowed(hours)
        for day in range(1, shift_obj.working_days + 1):
            lesson_occupied = {}
            day_terms = []
            for lesson in range(lesson_start, lesson_end):
                terms = []
                for ui in uidxs:
                    for slot in feasible_slots_by_unit[ui]:
                        if slot.day == day and slot.lesson == lesson:
                            key = (ui, slot.slot_id)
                            if key in x:
                                terms.append(x[key])
                occ = model.NewBoolVar(f"asg_occ_a{a.id}_d{day}_l{lesson}")
                if terms:
                    model.Add(sum(terms) >= occ)
                    model.Add(sum(terms) <= len(terms) * occ)
                    day_terms.extend(terms)
                else:
                    model.Add(occ == 0)
                lesson_occupied[lesson] = occ

            is_two = model.NewBoolVar(f"asg_two_a{a.id}_d{day}")
            is_one = model.NewBoolVar(f"asg_one_a{a.id}_d{day}")
            if day_terms:
                day_count = model.NewIntVar(0, max_per_subject_day, f"asg_cnt_a{a.id}_d{day}")
                model.Add(day_count == sum(day_terms))
                model.Add(day_count == 2).OnlyEnforceIf(is_two)
                model.Add(day_count != 2).OnlyEnforceIf(is_two.Not())
                model.Add(day_count == 1).OnlyEnforceIf(is_one)
                model.Add(day_count != 1).OnlyEnforceIf(is_one.Not())
            else:
                model.Add(is_two == 0)
                model.Add(is_one == 0)

            adjacent_bools = []
            for lesson in range(lesson_start, lesson_end - 1):
                b = model.NewBoolVar(f"asg_adj_a{a.id}_d{day}_l{lesson}")
                l1 = lesson_occupied[lesson]
                l2 = lesson_occupied[lesson + 1]
                model.Add(b <= l1)
                model.Add(b <= l2)
                model.Add(b >= l1 + l2 - 1)
                adjacent_bools.append(b)

            has_adjacent = model.NewBoolVar(f"asg_hasadj_a{a.id}_d{day}")
            if adjacent_bools:
                model.Add(has_adjacent <= sum(adjacent_bools))
                for b in adjacent_bools:
                    model.Add(has_adjacent >= b)
            else:
                model.Add(has_adjacent == 0)

            model.Add(is_two <= has_adjacent)

            is_one_vars.append(is_one)

        if not is_one_vars:
            continue
        if hard_pack:
            model.Add(sum(is_one_vars) == leftover)
        elif w_extra:
            extra = model.NewIntVar(0, shift_obj.working_days, f"asg_extra_a{a.id}")
            model.Add(extra >= sum(is_one_vars) - leftover)
            obj_terms.append(extra * w_extra)


# Model per-hour room bools only for small pools (labs). Wide general-room
# pools are assigned after Solve — otherwise y-vars blow up and phase 1
# misses the time limit.
_ROOM_MODEL_MAX_CANDIDATES = 4


def _slot_busy_fact(slot: SlotFact, classroom_id: int) -> BusySlotFact:
    return BusySlotFact(
        shift_id=slot.shift_id,
        day=slot.day,
        lesson=slot.lesson,
        interval=slot.interval,
        classroom_id=classroom_id,
    )


def _room_free_at(room_id: int, slot: SlotFact, caps: dict[int, int], busy: dict) -> bool:
    return not classroom_at_capacity(
        slot, room_id, busy, caps.get(room_id, 1)
    )


def _first_free_room(
    cands: list[tuple[int, int]],
    slots: list[SlotFact],
    caps: dict[int, int],
    busy: dict,
) -> int | None:
    for rid, _cost in cands:
        if all(_room_free_at(rid, s, caps, busy) for s in slots):
            return rid
    return None


def _occupy_room(busy: dict, room_id: int, slot: SlotFact) -> None:
    busy.setdefault(room_id, []).append(_slot_busy_fact(slot, room_id))


def _assign_rooms_to_chosen(
    chosen: list[tuple[int, Any, SlotFact]],
    *,
    candidates_by_assignment: dict[int, list[tuple[int, int]]],
    rooms: list[Any],
    busy: dict,
) -> dict[int, int] | None:
    """Greedy rooms for CP-SAT slots. Consecutive hours of one assignment
    share a room when one is free on both; otherwise each hour is picked
    separately. None if any hour has no free candidate.
    """
    caps = {r.id: (r.classes_capacity or 1) for r in rooms}
    rows = sorted(
        chosen,
        key=lambda t: (t[1].id, t[2].day, t[2].lesson, t[0]),
    )
    by_ui: dict[int, int] = {}
    i = 0
    while i < len(rows):
        ui, assignment, slot = rows[i]
        cands = candidates_by_assignment.get(assignment.id, [])
        paired = None
        if i + 1 < len(rows):
            ui2, a2, slot2 = rows[i + 1]
            if (
                a2.id == assignment.id
                and slot2.day == slot.day
                and slot2.lesson == slot.lesson + 1
            ):
                paired = (ui2, slot2)
        if paired is not None:
            ui2, slot2 = paired
            rid = _first_free_room(cands, [slot, slot2], caps, busy)
            if rid is not None:
                by_ui[ui] = rid
                by_ui[ui2] = rid
                _occupy_room(busy, rid, slot)
                _occupy_room(busy, rid, slot2)
                i += 2
                continue
        rid = _first_free_room(cands, [slot], caps, busy)
        if rid is None:
            return None
        by_ui[ui] = rid
        _occupy_room(busy, rid, slot)
        i += 1
    return by_ui


@dataclass
class SolveResult:
    placed_count: int
    placements: list
    unplaced: list
    diagnostics: list


class ResidualGraphSolver:
    """
    Residual bipartite solver:
    - left: remaining assignment-hour units
    - right: class/day/lesson slots
    """

    def __init__(self, classroom_resolver, session, school_id: int):
        self.session = session
        self.school_id = school_id
        self.validator = ScheduleValidator(self.session, school_id=school_id)
        self._classroom_resolver = classroom_resolver
        self._schedule = ScheduleService(session, school_id)

    def _build_edges(
        self,
        units,
        slots_by_class,
        assignment_map,
        school_level,
        *,
        teacher_busy,
        classroom_busy,
        class_occupancy,
        classroom_caps,
        candidates_by_assignment,
        max_per_subject_day,
        subject_day_counts,
        teacher_class_day_counts,
    ):
        adjacency = defaultdict(list)
        diagnostics_raw = defaultdict(Counter)
        feasible_by_assignment = Counter()

        for unit in units:
            assignment = assignment_map[unit.assignment_id]
            candidates = candidates_by_assignment.get(assignment.id, [])
            for slot in slots_by_class.get(unit.class_id, []):
                reason = None
                for occupied in class_occupancy.get(unit.class_id, []):
                    if occupancy_blocks_unit(unit, occupied, candidate_slot=slot):
                        reason = "Класс уже занят в это время"
                        break
                if reason is None and teacher_busy_at_slot(
                    slot, unit.teacher_id, teacher_busy
                ):
                    reason = "Учитель уже занят в это время"
                if reason is None and candidates:
                    has_free = False
                    for room_id, _cost in candidates:
                        cap = classroom_caps.get(room_id, 1)
                        if not classroom_at_capacity(
                            slot, room_id, classroom_busy, cap
                        ):
                            has_free = True
                            break
                    if not has_free:
                        reason = "Кабинет уже занят в это время"
                elif reason is None and not candidates:
                    reason = MSG_NO_CLASSROOM
                if reason is None:
                    subj_key = (unit.assignment_id, slot.day)
                    if subject_day_limit_reached(
                        subject_day_counts.get(subj_key, 0), max_per_subject_day
                    ):
                        reason = "Лимит уроков по предмету в этот день"
                    elif max_per_subject_day >= 2:
                        existing = [
                            occ.lesson
                            for occ in class_occupancy.get(unit.class_id, [])
                            if occ.assignment_id == unit.assignment_id and occ.day == slot.day
                        ]
                        if second_hour_is_split(existing, slot.lesson):
                            reason = "Сдвоенные уроки должны идти подряд"
                if reason is None and unit.teacher_id:
                    tc_key = (unit.teacher_id, unit.class_id, slot.day)
                    if teacher_class_day_limit_reached(
                        teacher_class_day_counts.get(tc_key, 0), 2
                    ):
                        reason = "Лимит учитель+класс в этот день"
                if reason is not None:
                    diagnostics_raw[assignment.id][reason] += 1
                    continue
                adjacency[unit.unit_id].append(slot.slot_id)
                feasible_by_assignment[assignment.id] += 1

        return adjacency, diagnostics_raw, feasible_by_assignment

    def _max_bipartite_matching(self, units, adjacency):
        match_slot_to_unit = {}

        def dfs(unit_id, visited):
            for slot_id in adjacency.get(unit_id, []):
                if slot_id in visited:
                    continue
                visited.add(slot_id)
                if slot_id not in match_slot_to_unit or dfs(match_slot_to_unit[slot_id], visited):
                    match_slot_to_unit[slot_id] = unit_id
                    return True
            return False

        for unit in units:
            dfs(unit.unit_id, set())

        match_unit_to_slot = {u: s for s, u in match_slot_to_unit.items()}
        return match_unit_to_slot

    def solve_residuals(
        self,
        school_level="elementary",
        teacher_id=None,
        class_id=None,
        max_diag_items=20,
        should_stop: Callable[[], bool] | None = None,
    ):
        assignment_query = self.session.query(TeachingAssignment).join(SchoolClass).filter(
            SchoolClass.school_level == school_level,
            TeachingAssignment.teacher_id.isnot(None),
            TeachingAssignment.school_id == self.school_id,
            SchoolClass.school_id == self.school_id,
        )
        if teacher_id:
            assignment_query = assignment_query.filter(TeachingAssignment.teacher_id == teacher_id)
        if class_id:
            assignment_query = assignment_query.filter(TeachingAssignment.class_id == class_id)

        raw = list(assignment_query.all())
        counts = placed_counts(self.session, [a.id for a in raw])
        assignments = [
            a for a in raw if remaining_for(a, placed=counts.get(a.id, 0)) > 0
        ]
        assignment_map = {a.id: a for a in assignments}
        if not assignments:
            return SolveResult(0, [], [], [])

        class_ids = sorted({a.class_id for a in assignments})
        classes = (
            self.session.query(SchoolClass)
            .filter(
                SchoolClass.id.in_(class_ids),
                SchoolClass.school_id == self.school_id,
            )
            .all()
            if class_ids
            else []
        )

        settings = load_settings(self.session, self.school_id, school_level)
        max_per_subject_day = settings.max_lessons_per_subject_per_day if settings else 2

        units = build_unit_facts(
            assignments,
            hours_mode="remaining",
            placed_counts=placed_counts(self.session, [a.id for a in assignments]),
        )
        slots_by_class = build_slots_by_class(
            classes,
            session=self.session,
            with_intervals=True,
            allow_default_grid=True,
        )

        rooms = load_classroom_facts(self.session, self.school_id)
        candidates_by_assignment: dict[int, list[tuple[int, int]]] = {}
        classroom_ids: set[int] = set()
        classroom_caps: dict[int, int] = {}
        for a in assignments:
            cands = candidate_classrooms(a, settings, rooms)
            candidates_by_assignment[a.id] = cands
            for rid, _cost in cands:
                classroom_ids.add(rid)
        for r in rooms:
            if r.id in classroom_ids:
                classroom_caps[r.id] = r.classes_capacity

        teacher_ids = {u.teacher_id for u in units if u.teacher_id}
        teacher_busy = load_teacher_busy(self.session, teacher_ids)
        classroom_busy = load_classroom_busy(self.session, classroom_ids)
        class_occupancy = load_class_occupancy(self.session, class_ids)

        subject_day_counts: dict[tuple[int, int], int] = Counter()
        for _cid, facts in class_occupancy.items():
            for fact in facts:
                if fact.assignment_id is not None:
                    subject_day_counts[(fact.assignment_id, fact.day)] += 1

        teacher_class_day_counts: dict[tuple[int, int, int], int] = Counter()
        for tid, facts in teacher_busy.items():
            for fact in facts:
                if fact.class_id is not None:
                    teacher_class_day_counts[(tid, fact.class_id, fact.day)] += 1

        adjacency, diagnostics_raw, feasible_by_assignment = self._build_edges(
            units,
            slots_by_class,
            assignment_map,
            school_level,
            teacher_busy=teacher_busy,
            classroom_busy=classroom_busy,
            class_occupancy=class_occupancy,
            classroom_caps=classroom_caps,
            candidates_by_assignment=candidates_by_assignment,
            max_per_subject_day=max_per_subject_day,
            subject_day_counts=subject_day_counts,
            teacher_class_day_counts=teacher_class_day_counts,
        )
        matched = self._max_bipartite_matching(units, adjacency)

        slot_map = {}
        for lst in slots_by_class.values():
            for slot in lst:
                slot_map[slot.slot_id] = slot

        unit_map = {u.unit_id: u for u in units}
        placements = []
        placed_count = 0

        # Re-validate while applying to keep hard constraints intact with newly added cells
        for unit_id, slot_id in matched.items():
            if should_stop and should_stop():
                break
            unit = unit_map[unit_id]
            slot = slot_map[slot_id]
            assignment = assignment_map[unit.assignment_id]
            classroom_id = self._classroom_resolver(
                assignment, school_level, day=slot.day, lesson=slot.lesson
            )
            errors = self.validator.validate_cell(
                assignment=assignment,
                day=slot.day,
                lesson=slot.lesson,
                classroom_id=classroom_id,
                require_classroom=True,
            )
            if errors:
                for err in errors:
                    diagnostics_raw[assignment.id][err] += 1
                continue

            self._schedule.insert_cell(
                class_id=assignment.class_id,
                day_of_week=slot.day,
                lesson_number=slot.lesson,
                assignment_id=assignment.id,
                classroom_id=classroom_id,
            )
            placements.append({
                "assignment_id": assignment.id,
                "class_id": assignment.class_id,
                "day": slot.day,
                "lesson": slot.lesson,
                "classroom_id": classroom_id,
            })
            placed_count += 1

        self.session.commit()

        # Refresh remaining and build diagnostics
        unplaced = []
        diagnostics = []
        rem_counts = placed_counts(
            self.session, [a.id for a in assignments]
        )
        for assignment in assignments:
            assignment = self.session.get(TeachingAssignment, assignment.id)
            rem = (
                remaining_for(assignment, placed=rem_counts.get(assignment.id, 0))
                if assignment
                else 0
            )
            if rem <= 0:
                continue
            unplaced.append({"assignment_id": assignment.id, "remaining_hours": rem})
            top_reasons = [
                {"reason": r, "count": c}
                for r, c in diagnostics_raw[assignment.id].most_common(3)
            ]
            diagnostics.append({
                "assignment_id": assignment.id,
                "class_name": assignment.school_class.name if assignment.school_class else "?",
                "subject_name": assignment.subject.display_name if assignment.subject else "?",
                "teacher_name": assignment.teacher.display_name if assignment.teacher else "?",
                "remaining_hours": rem,
                "feasible_slots": feasible_by_assignment[assignment.id],
                "top_reasons": top_reasons,
            })

        diagnostics.sort(key=lambda x: (-x["remaining_hours"], x["feasible_slots"], x["class_name"]))
        diagnostics = diagnostics[:max_diag_items]

        return SolveResult(
            placed_count=placed_count,
            placements=placements,
            unplaced=unplaced,
            diagnostics=diagnostics,
        )


@dataclass
class CpSatSolveResult:
    """Result of CP-SAT optimization for one shift."""

    status: str  # OPTIMAL, FEASIBLE, INFEASIBLE, UNKNOWN, MODEL_INVALID, ERROR, CANCELLED
    solver_status: str | None = None
    objective: int | None = None
    wall_time_sec: float | None = None
    placed_count: int = 0
    placements: list = field(default_factory=list)
    diagnostics: list = field(default_factory=list)
    error_message: str | None = None


@dataclass
class _ShiftDataContext:
    shift_classes: list[SchoolClass]
    class_ids: list[int]
    settings: Any
    max_per_subject_day: int
    assignments: list[TeachingAssignment]
    assignment_map: dict[int, TeachingAssignment]
    shift_obj: Any
    units: list[UnitFact]
    unit_list: list[tuple[int, UnitFact]]
    unit_by_idx: dict[int, UnitFact]
    slots_by_class: dict[int, list[SlotFact]]
    rooms: list[Any]
    candidates_by_assignment: dict[int, list[tuple[int, int]]]


@dataclass
class _HardModelContext:
    x: dict[tuple[int, str], Any]
    y: dict[tuple[int, str, int], Any]
    feasible_slots_by_unit: dict[int, list[SlotFact]]
    modeled_room_ids: set[int]
    subgroup_pairs: list[tuple[TeachingAssignment, TeachingAssignment]]


class CpSatScheduleSolver:
    """
    CP-SAT solver for a single shift: rebuilds all cells for classes in the shift
    (clear + re-place) with hard constraints aligned to ScheduleValidator rules.
    Search is staged: hard feasibility, then cumulative soft packages with hints.
    """

    def __init__(
        self,
        classroom_resolver: Callable[[TeachingAssignment, str], int | None],
        session,
        school_id: int,
    ):
        self.session = session
        self.school_id = school_id
        self.validator = ScheduleValidator(self.session, school_id=school_id)
        self._classroom_resolver = classroom_resolver
        self._schedule = ScheduleService(session, school_id)

    _STAGE_MIN_REMAINING_SEC = 0.5

    def _cancelled_result(self, should_stop) -> CpSatSolveResult | None:
        if should_stop and should_stop():
            return CpSatSolveResult(status="CANCELLED")
        return None

    def _notify(
        self,
        on_progress: Callable[[int, int, str], None] | None,
        current: int,
        total: int,
        message: str,
    ) -> None:
        if not on_progress:
            return
        try:
            on_progress(current, total, message)
        except Exception:
            pass

    def _release_db_lock(self) -> None:
        """End the solver session snapshot so cancel/progress can write (SQLite)."""
        try:
            self.session.commit()
        except Exception:
            try:
                self.session.rollback()
            except Exception:
                pass

    def _solve_with_cancel(self, solver, model, should_stop) -> Any:
        watcher_stop = threading.Event()
        watcher: threading.Thread | None = None

        def _watch_cancel() -> None:
            while not watcher_stop.is_set():
                try:
                    if should_stop and should_stop():
                        stop = getattr(solver, "StopSearch", None)
                        if callable(stop):
                            stop()
                        return
                except Exception:
                    pass
                if watcher_stop.wait(0.15):
                    return

        self._release_db_lock()
        if should_stop:
            watcher = threading.Thread(
                target=_watch_cancel, daemon=True, name="cp-sat-cancel"
            )
            watcher.start()
        try:
            return solver.Solve(model)
        finally:
            watcher_stop.set()
            if watcher is not None:
                watcher.join(timeout=1.5)

    def _run_staged_search(
        self,
        model,
        x: dict,
        y: dict,
        soft_stages: list[tuple[str, list]],
        time_limit_sec: float,
        random_seed: int,
        should_stop,
        on_progress: Callable[[int, int, str], None] | None = None,
        pair_freeze: PairFreezeSpec | None = None,
    ) -> tuple[str | None, Any, Any, float]:
        return run_staged_cp_sat_search(
            model,
            hint_maps=(x, y),
            soft_stages=soft_stages,
            time_limit_sec=time_limit_sec,
            random_seed=random_seed,
            num_workers=Config.SOLVER_NUM_WORKERS,
            min_remaining_sec=self._STAGE_MIN_REMAINING_SEC,
            should_stop=should_stop,
            on_progress=on_progress,
            solve_fn=lambda solver, m: self._solve_with_cancel(solver, m, should_stop),
            pair_freeze=pair_freeze,
        )

    def _load_shift_data(
        self,
        shift_id: int,
        school_level: str,
        class_ids: list[int] | None,
        max_diag_items: int,
        on_progress: Callable[[int, int, str], None] | None,
        should_stop: Callable[[], bool] | None,
    ) -> tuple[CpSatSolveResult | None, _ShiftDataContext | None]:
        shift_classes = (
            self.session.query(SchoolClass)
            .filter_by(
                shift_id=shift_id,
                school_level=school_level,
                school_id=self.school_id,
            )
            .order_by(SchoolClass.grade, SchoolClass.name)
            .all()
        )
        if class_ids is not None:
            allowed = set(class_ids)
            shift_classes = [c for c in shift_classes if c.id in allowed]
        if not shift_classes:
            return (
                CpSatSolveResult(
                    status="MODEL_INVALID",
                    diagnostics=[{"reason": "Нет классов для этой смены и уровня школы"}],
                ),
                None,
            )

        resolved_class_ids = [c.id for c in shift_classes]
        settings = load_settings(self.session, self.school_id, school_level)
        max_per_subject_day = settings.max_lessons_per_subject_per_day if settings else 2

        assignments = (
            self.session.query(TeachingAssignment)
            .options(
                joinedload(TeachingAssignment.teacher),
                joinedload(TeachingAssignment.school_class),
                joinedload(TeachingAssignment.subject),
            )
            .filter(
                TeachingAssignment.class_id.in_(resolved_class_ids),
                TeachingAssignment.teacher_id.isnot(None),
                TeachingAssignment.hours_per_week > 0,
                TeachingAssignment.school_id == self.school_id,
            )
            .all()
        )
        assignment_map = {a.id: a for a in assignments}

        if not assignments:
            return (
                CpSatSolveResult(
                    status="MODEL_INVALID",
                    diagnostics=[{"reason": "Нет назначений с учителем для классов смены"}],
                ),
                None,
            )

        shift_obj = shift_classes[0].shift
        if not shift_obj:
            return (
                CpSatSolveResult(
                    status="MODEL_INVALID",
                    diagnostics=[{"reason": "Смена не найдена"}],
                ),
                None,
            )
        n_shift_slots = int(shift_obj.working_days) * int(shift_obj.lessons_count)
        hours_by_tid: dict[int, int] = defaultdict(int)
        name_by_tid: dict[int, str] = {}
        for a in assignments:
            tid = a.teacher_id
            if not tid:
                continue
            hours_by_tid[tid] += int(a.hours_per_week or 0)
            if tid not in name_by_tid:
                teacher = a.teacher
                name_by_tid[tid] = teacher.display_name if teacher else f"#{tid}"
        overload_diag: list[dict[str, str]] = []
        for tid, hours in sorted(hours_by_tid.items(), key=lambda kv: -kv[1]):
            if hours <= n_shift_slots:
                continue
            name = name_by_tid.get(tid) or f"#{tid}"
            overload_diag.append(
                {
                    "reason": (
                        f"У учителя {name} в этой смене {hours} ч, "
                        f"а слотов в сетке смены только {n_shift_slots} "
                        f"({shift_obj.working_days} дн. × {shift_obj.lessons_count} ур.). "
                        "Составление остановлено: нагрузка не помещается в смену."
                    )
                }
            )
        if overload_diag:
            return (
                CpSatSolveResult(
                    status="INFEASIBLE",
                    diagnostics=overload_diag[:max_diag_items],
                ),
                None,
            )

        n_hours = sum(int(a.hours_per_week or 0) for a in assignments)
        self._notify(
            on_progress,
            10,
            100,
            (
                f"Смена «{shift_obj.name}»: {len(shift_classes)} кл., "
                f"{n_hours} ч, {len(hours_by_tid)} учителей"
            ),
        )

        stopped = self._cancelled_result(should_stop)
        if stopped:
            return stopped, None

        units = build_unit_facts(assignments, hours_mode="full")
        if not units:
            return (
                CpSatSolveResult(
                    status="MODEL_INVALID",
                    diagnostics=[{"reason": "Нет часов для размещения"}],
                ),
                None,
            )

        self._notify(
            on_progress,
            18,
            100,
            f"Сборка модели: {len(units)} уроков-часов…",
        )

        slots_by_class: dict[int, list[SlotFact]] = build_slots_by_class(
            shift_classes, session=self.session, with_intervals=True
        )

        # --- feasibility: enough slots per class
        for a in assignments:
            n_slots = len(slots_by_class.get(a.class_id, []))
            if a.hours_per_week > n_slots:
                return (
                    CpSatSolveResult(
                        status="INFEASIBLE",
                        diagnostics=[
                            {
                                "reason": (
                                    f"Назначение {a.id}: требуется {a.hours_per_week} ч/н, "
                                    f"слотов в сетке класса только {n_slots}"
                                )
                            }
                        ],
                    ),
                    None,
                )

        rooms = load_classroom_facts(self.session, self.school_id)
        candidates_by_assignment: dict[int, list[tuple[int, int]]] = {
            a.id: candidate_classrooms(a, settings, rooms) for a in assignments
        }
        missing_rooms: list[dict[str, str]] = []
        for a in assignments:
            if candidates_by_assignment.get(a.id):
                continue
            class_name = a.school_class.name if a.school_class else "?"
            subj_name = a.subject.display_name if a.subject else "?"
            missing_rooms.append(
                {
                    "reason": (
                        f"{class_name} «{subj_name}»: {MSG_NO_CLASSROOM}"
                    )
                }
            )
        if missing_rooms:
            return (
                CpSatSolveResult(
                    status="INFEASIBLE",
                    diagnostics=missing_rooms[:max_diag_items],
                ),
                None,
            )

        unit_list = list(enumerate(units))
        unit_by_idx = {i: u for i, u in unit_list}

        ctx = _ShiftDataContext(
            shift_classes=shift_classes,
            class_ids=resolved_class_ids,
            settings=settings,
            max_per_subject_day=max_per_subject_day,
            assignments=assignments,
            assignment_map=assignment_map,
            shift_obj=shift_obj,
            units=units,
            unit_list=unit_list,
            unit_by_idx=unit_by_idx,
            slots_by_class=slots_by_class,
            rooms=rooms,
            candidates_by_assignment=candidates_by_assignment,
        )
        return None, ctx

    def _build_hard_model(
        self,
        model: cp_model.CpModel,
        ctx: _ShiftDataContext,
        should_stop: Callable[[], bool] | None,
    ) -> tuple[CpSatSolveResult | None, _HardModelContext | None]:
        teacher_ids_scope = {u.teacher_id for u in ctx.units if u.teacher_id}
        external_busy = load_external_teacher_busy(
            self.session, teacher_ids_scope, ctx.class_ids
        )

        x: dict[tuple[int, str], cp_model.IntVar] = {}
        feasible_slots_by_unit: dict[int, list[SlotFact]] = {}

        for ui, unit in ctx.unit_list:
            slot_list = ctx.slots_by_class.get(unit.class_id, [])
            if not slot_list:
                return (
                    CpSatSolveResult(
                        status="INFEASIBLE",
                        diagnostics=[{"reason": f"Нет слотов для класса {unit.class_id}"}],
                    ),
                    None,
                )
            feasible = [
                s
                for s in slot_list
                if not teacher_busy_at_slot(s, unit.teacher_id, external_busy)
            ]
            if not feasible:
                return (
                    CpSatSolveResult(
                        status="INFEASIBLE",
                        diagnostics=[
                            {
                                "reason": (
                                    f"Нет свободных слотов для часа {unit.unit_id} "
                                    f"(учитель занят вне этой смены во всех пересечениях по времени)"
                                )
                            }
                        ],
                    ),
                    None,
                )
            feasible_slots_by_unit[ui] = feasible
            for slot in feasible:
                x[(ui, slot.slot_id)] = model.NewBoolVar(f"u{ui}_{slot.slot_id}")
            if ui % 40 == 0:
                stopped = self._cancelled_result(should_stop)
                if stopped:
                    return stopped, None

        for ui, unit in ctx.unit_list:
            feas = feasible_slots_by_unit[ui]
            model.AddExactlyOne([x[(ui, s.slot_id)] for s in feas])

        y: dict[tuple[int, str, int], Any] = {}
        modeled_room_ids: set[int] = set()
        for ui, unit in ctx.unit_list:
            a = ctx.assignment_map[unit.assignment_id]
            cands = ctx.candidates_by_assignment.get(a.id, [])
            if not cands or len(cands) > _ROOM_MODEL_MAX_CANDIDATES:
                continue
            for slot in feasible_slots_by_unit[ui]:
                key = (ui, slot.slot_id)
                if key not in x:
                    continue
                y_vars = []
                for rid, _cost in cands:
                    yv = model.NewBoolVar(f"y_u{ui}_{slot.slot_id}_r{rid}")
                    y[(ui, slot.slot_id, rid)] = yv
                    y_vars.append(yv)
                    modeled_room_ids.add(rid)
                model.Add(sum(y_vars) == x[key])

        # Same class slot: conflicting pairs cannot share slot
        by_class: dict[int, list[int]] = defaultdict(list)
        for ui, unit in ctx.unit_list:
            by_class[unit.class_id].append(ui)

        for cid, idxs in by_class.items():
            slot_list = ctx.slots_by_class[cid]
            for i_a in range(len(idxs)):
                for i_b in range(i_a + 1, len(idxs)):
                    uia, uib = idxs[i_a], idxs[i_b]
                    if not units_cannot_share_class_slot(
                        ctx.unit_by_idx[uia], ctx.unit_by_idx[uib]
                    ):
                        continue
                    for slot in slot_list:
                        key_a = (uia, slot.slot_id)
                        key_b = (uib, slot.slot_id)
                        if key_a not in x or key_b not in x:
                            continue
                        model.Add(x[key_a] + x[key_b] <= 1)

        # Hard: class day is a prefix of the shift grid (start_lesson … last used).
        lesson_start = ctx.shift_obj.start_lesson
        lesson_end = ctx.shift_obj.start_lesson + ctx.shift_obj.lessons_count
        for cid in ctx.class_ids:
            uidxs = [ui for ui, u in ctx.unit_list if u.class_id == cid]
            if not uidxs:
                continue
            for day in range(1, ctx.shift_obj.working_days + 1):
                occ_by_lesson = {}
                for lesson in range(lesson_start, lesson_end):
                    terms = []
                    for ui in uidxs:
                        for slot in feasible_slots_by_unit[ui]:
                            if slot.day == day and slot.lesson == lesson:
                                key = (ui, slot.slot_id)
                                if key in x:
                                    terms.append(x[key])
                    occ = model.NewBoolVar(f"class_occ_c{cid}_d{day}_l{lesson}")
                    if terms:
                        dsum = sum(terms)
                        model.Add(dsum >= occ)
                        model.Add(dsum <= len(terms) * occ)
                    else:
                        model.Add(occ == 0)
                    occ_by_lesson[lesson] = occ

                for lesson in range(lesson_start + 1, lesson_end):
                    model.Add(occ_by_lesson[lesson] <= occ_by_lesson[lesson - 1])

        # Teacher: at most one overlapping lesson across all classes in this shift
        by_teacher: dict[int, list[int]] = defaultdict(list)
        for ui, unit in ctx.unit_list:
            if unit.teacher_id:
                by_teacher[unit.teacher_id].append(ui)

        for _tid, uidxs in by_teacher.items():
            items: list[tuple[Any, SlotFact]] = []
            for ui in uidxs:
                for slot in feasible_slots_by_unit[ui]:
                    key = (ui, slot.slot_id)
                    if key in x:
                        items.append((x[key], slot))
            _add_capacity_overlap_constraints(model, items, capacity=1)

        # Classroom: respect capacity only for small modeled pools
        room_caps = {r.id: (r.classes_capacity or 1) for r in ctx.rooms}
        for room_id in modeled_room_ids:
            cap_n = room_caps.get(room_id, 1)
            if cap_n >= 10**5:
                continue
            items = []
            for ui, unit in ctx.unit_list:
                for slot in feasible_slots_by_unit[ui]:
                    ykey = (ui, slot.slot_id, room_id)
                    if ykey in y:
                        items.append((y[ykey], slot))
            _add_capacity_overlap_constraints(model, items, capacity=cap_n)

        total_seats = sum(max(1, r.classes_capacity or 1) for r in ctx.rooms)
        if total_seats:
            by_dl: dict[tuple[int, int], list] = defaultdict(list)
            for ui, unit in ctx.unit_list:
                for slot in feasible_slots_by_unit[ui]:
                    key = (ui, slot.slot_id)
                    if key in x:
                        by_dl[(slot.day, slot.lesson)].append(x[key])
            for vars_ in by_dl.values():
                model.Add(sum(vars_) <= total_seats)

        fixed_pool_cap: dict[int, int] = {}
        for a in ctx.assignments:
            subj = a.subject
            if not subj or not subj.requires_fixed_classroom:
                continue
            cands = ctx.candidates_by_assignment.get(a.id, [])
            fixed_pool_cap[subj.id] = sum(
                max(1, room_caps.get(rid, 1)) for rid, _ in cands
            )
        for sid, pool_cap in fixed_pool_cap.items():
            if pool_cap <= 0:
                continue
            by_dl_s: dict[tuple[int, int], list] = defaultdict(list)
            for ui, unit in ctx.unit_list:
                if unit.subject_id != sid:
                    continue
                for slot in feasible_slots_by_unit[ui]:
                    key = (ui, slot.slot_id)
                    if key in x:
                        by_dl_s[(slot.day, slot.lesson)].append(x[key])
            for vars_ in by_dl_s.values():
                model.Add(sum(vars_) <= pool_cap)

        # Max lessons per subject per day (per assignment)
        for a in ctx.assignments:
            uidxs = [ui for ui, u in ctx.unit_list if u.assignment_id == a.id]
            for day in range(1, ctx.shift_obj.working_days + 1):
                terms = []
                for ui in uidxs:
                    for slot in feasible_slots_by_unit[ui]:
                        if slot.day == day:
                            key = (ui, slot.slot_id)
                            if key in x:
                                terms.append(x[key])
                if terms:
                    model.Add(sum(terms) <= ctx.max_per_subject_day)

        # Subgroup pair synchronization (hard)
        subgroup_pairs = []
        by_class_subject: dict[tuple[int, int], list[TeachingAssignment]] = defaultdict(list)
        for a in ctx.assignments:
            if a.group_number is not None:
                by_class_subject[(a.class_id, a.subject_id)].append(a)
        for (_cid, _sid), rows in by_class_subject.items():
            rows = sorted(rows, key=lambda x: (x.group_number or 0, x.id))
            for i in range(len(rows)):
                for j in range(i + 1, len(rows)):
                    if rows[i].group_number == rows[j].group_number:
                        continue
                    subgroup_pairs.append((rows[i], rows[j]))

        for a1, a2 in subgroup_pairs:
            uidxs1 = [ui for ui, u in ctx.unit_list if u.assignment_id == a1.id]
            uidxs2 = [ui for ui, u in ctx.unit_list if u.assignment_id == a2.id]
            if not uidxs1 or not uidxs2:
                continue
            for day in range(1, ctx.shift_obj.working_days + 1):
                for lesson in range(lesson_start, lesson_end):
                    terms1 = []
                    for ui in uidxs1:
                        for slot in feasible_slots_by_unit[ui]:
                            if slot.day == day and slot.lesson == lesson:
                                key = (ui, slot.slot_id)
                                if key in x:
                                    terms1.append(x[key])
                    terms2 = []
                    for ui in uidxs2:
                        for slot in feasible_slots_by_unit[ui]:
                            if slot.day == day and slot.lesson == lesson:
                                key = (ui, slot.slot_id)
                                if key in x:
                                    terms2.append(x[key])
                    if terms1 or terms2:
                        model.Add(sum(terms1) == sum(terms2))

        # For secondary/high school, avoid giving one teacher > 2 lessons in one class in a single day
        # unless their total weekly hours in this class exceed 2 * working_days (e.g. primary homeroom teachers).
        teacher_class_days: set[tuple[int, int]] = set()
        teacher_class_hours: dict[tuple[int, int], int] = defaultdict(int)
        for a in ctx.assignments:
            if a.teacher_id:
                teacher_class_days.add((a.teacher_id, a.class_id))
                teacher_class_hours[(a.teacher_id, a.class_id)] += int(a.hours_per_week or 0)

        for tid, cid in teacher_class_days:
            total_hours = teacher_class_hours[(tid, cid)]
            # If teacher has > 2 * working_days hours in this class, allow more lessons per day
            max_daily_teacher = max(2, (total_hours + ctx.shift_obj.working_days - 1) // ctx.shift_obj.working_days)
            for day in range(1, ctx.shift_obj.working_days + 1):
                terms = []
                for ui, unit in ctx.unit_list:
                    if unit.teacher_id != tid or unit.class_id != cid:
                        continue
                    for slot in feasible_slots_by_unit[ui]:
                        if slot.day == day:
                            key = (ui, slot.slot_id)
                            if key in x:
                                terms.append(x[key])
                if terms:
                    model.Add(sum(terms) <= max_daily_teacher)

        hard_ctx = _HardModelContext(
            x=x,
            y=y,
            feasible_slots_by_unit=feasible_slots_by_unit,
            modeled_room_ids=modeled_room_ids,
            subgroup_pairs=subgroup_pairs,
        )
        return None, hard_ctx

    def _build_soft_packages(
        self,
        model: cp_model.CpModel,
        ctx: _ShiftDataContext,
        hard_ctx: _HardModelContext,
        hours_first: str,
    ) -> tuple[dict[str, list[Any]], PairFreezeSpec | None]:
        prefs = weights_from_settings(ctx.settings)
        scales = solver_scales(prefs)
        packages = empty_soft_packages()
        pack_gaps = packages[SOFT_STAGE_PACK_GAPS]
        early_rooms = packages[SOFT_STAGE_EARLY_ROOMS]
        cosmetics = packages[SOFT_STAGE_COSMETICS]

        w_slot = scales.slot
        w_balance = scales.day_balance
        w_subgroup_spread = scales.subgroup_spread
        w_room = scales.room_placement
        for ui, unit in ctx.unit_list:
            a = ctx.assignment_map.get(unit.assignment_id)
            subj = a.subject if a else None
            difficulty = getattr(subj, "difficulty", "medium") if subj else "medium"
            is_hard = difficulty == "hard"
            is_easy = difficulty == "easy"

            for slot in hard_ctx.feasible_slots_by_unit[ui]:
                key = (ui, slot.slot_id)
                if key not in hard_ctx.x:
                    continue
                weight = slot.day * 100 + slot.lesson
                if slot.lesson >= 7:
                    # Deterrent penalty for 7th+ lessons: place them last, only when unavoidable
                    weight += 10000 * (slot.lesson - 6) + scales.late_lesson * 2
                    if is_hard:
                        # Heavy deterrent penalty against placing hard subjects on 7th+ lessons
                        weight += 50000
                elif slot.lesson >= 6:
                    weight += scales.late_lesson * (slot.lesson - 5)
                    if is_hard:
                        weight += scales.late_lesson * 2

                if is_hard:
                    # Extra preference to place hard subjects earlier (lessons 1-4)
                    weight += slot.lesson * 25
                elif is_easy:
                    # Easy subjects get small discount on later lessons to absorb late slots
                    weight = max(1, weight - slot.lesson * 5)

                early_rooms.append(hard_ctx.x[key] * weight * w_slot)

        # Prefer owner / same-subject rooms
        for ui, unit in ctx.unit_list:
            a = ctx.assignment_map[unit.assignment_id]
            cands = ctx.candidates_by_assignment.get(a.id, [])
            for rid, cost in cands:
                if cost <= 0:
                    continue
                for slot in hard_ctx.feasible_slots_by_unit[ui]:
                    ykey = (ui, slot.slot_id, rid)
                    if ykey in hard_ctx.y:
                        early_rooms.append(hard_ctx.y[ykey] * cost * w_room)

        # Penalize uneven distribution across days per class
        for cid in ctx.class_ids:
            uidxs = [ui for ui, u in ctx.unit_list if u.class_id == cid]
            if not uidxs:
                continue
            for day in range(1, ctx.shift_obj.working_days + 1):
                day_terms = []
                for ui in uidxs:
                    for slot in hard_ctx.feasible_slots_by_unit[ui]:
                        if slot.day == day:
                            key = (ui, slot.slot_id)
                            if key in hard_ctx.x:
                                day_terms.append(hard_ctx.x[key])
                if day_terms:
                    dsum = sum(day_terms)
                    for day2 in range(day + 1, ctx.shift_obj.working_days + 1):
                        day2_terms = []
                        for ui in uidxs:
                            for slot in hard_ctx.feasible_slots_by_unit[ui]:
                                if slot.day == day2:
                                    key = (ui, slot.slot_id)
                                    if key in hard_ctx.x:
                                        day2_terms.append(hard_ctx.x[key])
                        if day2_terms:
                            diff = model.NewIntVar(-len(uidxs), len(uidxs), f"diff_{cid}_{day}_{day2}")
                            model.Add(diff == dsum - sum(day2_terms))
                            abs_diff = model.NewIntVar(0, len(uidxs), f"abs_{cid}_{day}_{day2}")
                            model.AddAbsEquality(abs_diff, diff)
                            cosmetics.append(abs_diff * w_balance)

        _add_assignment_pair_packing(
            model,
            assignments=ctx.assignments,
            unit_list=ctx.unit_list,
            feasible_slots_by_unit=hard_ctx.feasible_slots_by_unit,
            x=hard_ctx.x,
            shift_obj=ctx.shift_obj,
            max_per_subject_day=ctx.max_per_subject_day,
            scales=scales,
            obj_terms=pack_gaps,
        )

        # Subgroup subjects: prefer concentrating lessons in fewer days
        subgroup_assignments = [a for a in ctx.assignments if a.group_number is not None]
        for a in subgroup_assignments:
            uidxs = [ui for ui, u in ctx.unit_list if u.assignment_id == a.id]
            for day in range(1, ctx.shift_obj.working_days + 1):
                day_terms = []
                for ui in uidxs:
                    for slot in hard_ctx.feasible_slots_by_unit[ui]:
                        if slot.day == day:
                            key = (ui, slot.slot_id)
                            if key in hard_ctx.x:
                                day_terms.append(hard_ctx.x[key])
                day_active = model.NewBoolVar(f"subgrp_a{a.id}_d{day}")
                if day_terms:
                    dsum = sum(day_terms)
                    model.Add(dsum >= day_active)
                    model.Add(dsum <= a.hours_per_week * day_active)
                else:
                    model.Add(day_active == 0)
                if w_subgroup_spread:
                    cosmetics.append(day_active * w_subgroup_spread)

        if scales.teacher_days:
            teacher_ids = {unit.teacher_id for _, unit in ctx.unit_list if unit.teacher_id}
            for tid in teacher_ids:
                for day in range(1, ctx.shift_obj.working_days + 1):
                    day_terms = []
                    for ui, unit in ctx.unit_list:
                        if unit.teacher_id != tid:
                            continue
                        for slot in hard_ctx.feasible_slots_by_unit[ui]:
                            if slot.day == day:
                                key = (ui, slot.slot_id)
                                if key in hard_ctx.x:
                                    day_terms.append(hard_ctx.x[key])
                    day_active = model.NewBoolVar(f"tdays_t{tid}_d{day}")
                    if day_terms:
                        dsum = sum(day_terms)
                        model.Add(dsum >= day_active)
                        model.Add(dsum <= len(day_terms) * day_active)
                    else:
                        model.Add(day_active == 0)
                    pack_gaps.append(day_active * scales.teacher_days)

        _add_hardest_first_decision_strategy(
            model,
            ctx.unit_list,
            hard_ctx.feasible_slots_by_unit,
            hard_ctx.x,
            hard_ctx.y,
            hours_by_assignment={
                int(a.id): int(a.hours_per_week or 0) for a in ctx.assignments
            },
            hours_first=normalize_hours_first(hours_first),
        )
        policy = freeze_policy(prefs)
        pair_freeze = None
        if policy.enabled:
            pair_freeze = PairFreezeSpec(
                x=hard_ctx.x,
                unit_list=ctx.unit_list,
                feasible_slots_by_unit=hard_ctx.feasible_slots_by_unit,
                paired_assignment_ids=tuple(
                    (a1.id, a2.id) for a1, a2 in hard_ctx.subgroup_pairs
                ),
                hard=policy.hard,
                max_pair_lesson=policy.max_pair_lesson,
                hours_by_assignment={
                    int(a.id): int(a.hours_per_week or 0) for a in ctx.assignments
                },
                min_hours=policy.min_hours,
            )
        return packages, pair_freeze

    def _run_search_and_apply(
        self,
        model: cp_model.CpModel,
        ctx: _ShiftDataContext,
        hard_ctx: _HardModelContext,
        packages: dict[str, list[Any]],
        pair_freeze: PairFreezeSpec | None,
        time_limit_sec: float,
        random_seed: int,
        max_diag_items: int,
        should_stop: Callable[[], bool] | None,
        on_progress: Callable[[int, int, str], None] | None,
        school_level: str,
    ) -> CpSatSolveResult:
        cancelled, status, solver, search_wall = self._run_staged_search(
            model,
            hard_ctx.x,
            hard_ctx.y,
            cumulative_soft_stages(packages),
            time_limit_sec=time_limit_sec,
            random_seed=random_seed,
            should_stop=should_stop,
            on_progress=on_progress,
            pair_freeze=pair_freeze,
        )
        if cancelled == "CANCELLED" or (should_stop and should_stop()):
            stopped = CpSatSolveResult(status="CANCELLED")
            if solver is not None and status is not None:
                stopped.solver_status = solver.StatusName(status)
            stopped.wall_time_sec = search_wall
            return stopped

        status_name = solver.StatusName(status)
        if status in (cp_model.INFEASIBLE, cp_model.MODEL_INVALID):
            diag = [
                {
                    "reason": (
                        "CP-SAT: модель неразрешима при заданных ограничениях "
                        f"(статус {status_name}). Проверьте часы учителей, "
                        "окна в сетке класса и кабинеты."
                    )
                }
            ]
            return CpSatSolveResult(
                status="INFEASIBLE",
                solver_status=status_name,
                wall_time_sec=search_wall,
                diagnostics=diag[:max_diag_items],
            )

        if status == cp_model.UNKNOWN:
            diag = [
                {
                    "reason": (
                        "CP-SAT завершился со статусом UNKNOWN (обычно по лимиту времени без найденного решения). "
                        "Попробуйте увеличить time_limit_sec или упростить область решения."
                    )
                }
            ]
            return CpSatSolveResult(
                status="UNKNOWN",
                solver_status=status_name,
                wall_time_sec=search_wall,
                diagnostics=diag[:max_diag_items],
            )

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return CpSatSolveResult(
                status="ERROR",
                solver_status=status_name,
                error_message=f"Неожиданный статус решателя: {status_name}",
            )

        # Apply: transaction — remove old cells for scope, insert new
        try:
            stopped = self._cancelled_result(should_stop)
            if stopped:
                return stopped
            self._notify(on_progress, 90, 100, "Запись расписания в сетку…")
            self._schedule.delete_cells(class_ids=ctx.class_ids, commit=False)

            chosen_rows: list[tuple[int, Any, SlotFact]] = []
            for ui, unit in ctx.unit_list:
                a = ctx.assignment_map[unit.assignment_id]
                chosen = None
                for slot in hard_ctx.feasible_slots_by_unit[ui]:
                    key = (ui, slot.slot_id)
                    if key not in hard_ctx.x:
                        continue
                    if solver.Value(hard_ctx.x[key]) == 1:
                        chosen = slot
                        break
                if not chosen:
                    self.session.rollback()
                    return CpSatSolveResult(
                        status="ERROR",
                        error_message=f"CP-SAT не выбрал слот для часа {unit.unit_id}",
                    )
                chosen_rows.append((ui, a, chosen))

            room_ids = {
                rid
                for cands in ctx.candidates_by_assignment.values()
                for rid, _ in cands
            }
            busy = load_classroom_busy(self.session, room_ids)
            rooms_by_ui = _assign_rooms_to_chosen(
                chosen_rows,
                candidates_by_assignment=ctx.candidates_by_assignment,
                rooms=ctx.rooms,
                busy=busy,
            )
            if rooms_by_ui is None:
                self.session.rollback()
                return CpSatSolveResult(
                    status="ERROR",
                    error_message=MSG_NO_CLASSROOM,
                )

            placements = []
            for ui, a, chosen in chosen_rows:
                classroom_id = rooms_by_ui.get(ui)
                if classroom_id is None:
                    self.session.rollback()
                    class_name = a.school_class.name if a.school_class else "?"
                    subj_name = a.subject.display_name if a.subject else "?"
                    return CpSatSolveResult(
                        status="ERROR",
                        error_message=(
                            f"{class_name} «{subj_name}»: {MSG_NO_CLASSROOM}"
                        ),
                    )
                self._schedule.insert_cell(
                    class_id=a.class_id,
                    day_of_week=chosen.day,
                    lesson_number=chosen.lesson,
                    assignment_id=a.id,
                    classroom_id=classroom_id,
                )
                placements.append(
                    {
                        "assignment_id": a.id,
                        "class_id": a.class_id,
                        "day": chosen.day,
                        "lesson": chosen.lesson,
                        "classroom_id": classroom_id,
                    }
                )

            self.session.commit()
        except Exception as ex:  # pragma: no cover
            self.session.rollback()
            return CpSatSolveResult(
                status="ERROR",
                error_message=str(ex),
            )

        objective_val = int(solver.ObjectiveValue()) if solver.ObjectiveValue() is not None else None

        return CpSatSolveResult(
            status="OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE",
            solver_status=status_name,
            objective=objective_val,
            wall_time_sec=search_wall,
            placed_count=len(placements),
            placements=placements,
            diagnostics=[],
        )

    def solve_shift(
        self,
        shift_id: int,
        school_level: str,
        time_limit_sec: float = 60.0,
        random_seed: int = 1,
        max_diag_items: int = 20,
        should_stop: Callable[[], bool] | None = None,
        on_progress: Callable[[int, int, str], None] | None = None,
        class_ids: list[int] | None = None,
        hours_first: str = HOURS_FIRST_MORE,
    ) -> CpSatSolveResult:
        """
        Rebuild schedule for classes in the given shift (same school_level).
        If ``class_ids`` is set, only those classes (must belong to the shift).
        Deletes existing cells for the scoped classes and writes new ones if feasible.
        """
        if cp_model is None:
            return CpSatSolveResult(
                status="ERROR",
                error_message="Пакет ortools не установлен. Выполните: pip install ortools",
            )

        err_res, ctx = self._load_shift_data(
            shift_id=shift_id,
            school_level=school_level,
            class_ids=class_ids,
            max_diag_items=max_diag_items,
            on_progress=on_progress,
            should_stop=should_stop,
        )
        if err_res is not None or ctx is None:
            return err_res

        model = cp_model.CpModel()
        hard_err, hard_ctx = self._build_hard_model(model, ctx, should_stop=should_stop)
        if hard_err is not None or hard_ctx is None:
            return hard_err

        packages, pair_freeze = self._build_soft_packages(
            model, ctx, hard_ctx, hours_first=hours_first
        )

        stopped = self._cancelled_result(should_stop)
        if stopped:
            return stopped

        return self._run_search_and_apply(
            model=model,
            ctx=ctx,
            hard_ctx=hard_ctx,
            packages=packages,
            pair_freeze=pair_freeze,
            time_limit_sec=time_limit_sec,
            random_seed=random_seed,
            max_diag_items=max_diag_items,
            should_stop=should_stop,
            on_progress=on_progress,
            school_level=school_level,
        )
