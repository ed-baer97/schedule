"""Staged CP-SAT search: feasibility first, then soft packages."""
import pytest

from app.domain.preferences import SOFT_STAGE_PACK_GAPS


def test_staged_search_optimizes_after_feasibility():
    pytest.importorskip("ortools")
    from ortools.sat.python import cp_model

    from app.services.schedule_solver import run_staged_cp_sat_search

    model = cp_model.CpModel()
    expensive = model.NewBoolVar("expensive")
    cheap = model.NewBoolVar("cheap")
    model.Add(expensive + cheap == 1)
    # Worker 0 tries expensive=1 first; phase 1 would keep it without Minimize.
    model.AddDecisionStrategy(
        [expensive, cheap],
        cp_model.CHOOSE_FIRST,
        cp_model.SELECT_MAX_VALUE,
    )
    cancelled, status, solver, _elapsed = run_staged_cp_sat_search(
        model,
        hint_maps=({"expensive": expensive, "cheap": cheap},),
        soft_stages=[(SOFT_STAGE_PACK_GAPS, [expensive * 10 + cheap * 1])],
        time_limit_sec=5.0,
        random_seed=1,
        num_workers=1,
    )
    assert cancelled is None
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    assert solver.Value(cheap) == 1
    assert solver.Value(expensive) == 0


def test_staged_search_tail_runs_after_named_packages():
    pytest.importorskip("ortools")
    from ortools.sat.python import cp_model

    from app.services.schedule_solver import run_staged_cp_sat_search

    model = cp_model.CpModel()
    expensive = model.NewBoolVar("expensive")
    cheap = model.NewBoolVar("cheap")
    model.Add(expensive + cheap == 1)
    model.AddDecisionStrategy(
        [expensive, cheap],
        cp_model.CHOOSE_FIRST,
        cp_model.SELECT_MAX_VALUE,
    )
    solves = {"n": 0}
    messages: list[str] = []

    def solve_fn(solver, _model):
        solves["n"] += 1
        return solver.Solve(model)

    cancelled, status, solver, _elapsed = run_staged_cp_sat_search(
        model,
        hint_maps=({"expensive": expensive, "cheap": cheap},),
        soft_stages=[(SOFT_STAGE_PACK_GAPS, [expensive * 10 + cheap * 1])],
        time_limit_sec=5.0,
        random_seed=1,
        num_workers=1,
        solve_fn=solve_fn,
        on_progress=lambda _c, _t, msg: messages.append(msg),
    )
    assert cancelled is None
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    assert solver.Value(cheap) == 1
    # feas + named package + at least one tail round
    assert solves["n"] >= 3
    assert any("Докручиваю" in msg for msg in messages)


def test_staged_search_feasibility_only_when_no_soft_terms():
    pytest.importorskip("ortools")
    from ortools.sat.python import cp_model

    from app.services.schedule_solver import run_staged_cp_sat_search

    model = cp_model.CpModel()
    a = model.NewBoolVar("a")
    model.Add(a == 1)
    cancelled, status, solver, _elapsed = run_staged_cp_sat_search(
        model,
        hint_maps=({"a": a},),
        soft_stages=[],
        time_limit_sec=2.0,
        random_seed=1,
        num_workers=1,
    )
    assert cancelled is None
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    assert solver.Value(a) == 1


def _unit(assignment_id: int, unit_id: str):
    from app.domain.schedule_facts import UnitFact

    return UnitFact(
        unit_id=unit_id,
        assignment_id=assignment_id,
        teacher_id=1,
        class_id=1,
        subject_id=1,
        group_number=None,
        school_level="elementary",
    )


class _FixedSolver:
    def __init__(self, values: dict) -> None:
        self._values = values

    def Value(self, var):
        return self._values[var]


def test_freeze_good_doubles_pins_early_pair():
    pytest.importorskip("ortools")
    from ortools.sat.python import cp_model

    from app.domain.pair_epochs import PairFreezeSpec
    from app.domain.schedule_facts import SlotFact
    from app.services.schedule_solver import _freeze_good_doubles

    model = cp_model.CpModel()
    s1 = SlotFact(slot_id="s1", class_id=1, day=1, lesson=1, shift_id=1)
    s2 = SlotFact(slot_id="s2", class_id=1, day=1, lesson=2, shift_id=1)
    s5 = SlotFact(slot_id="s5", class_id=1, day=1, lesson=5, shift_id=1)
    s6 = SlotFact(slot_id="s6", class_id=1, day=1, lesson=6, shift_id=1)
    x01 = model.NewBoolVar("u0_s1")
    x05 = model.NewBoolVar("u0_s5")
    x12 = model.NewBoolVar("u1_s2")
    x16 = model.NewBoolVar("u1_s6")
    model.Add(x01 + x05 == 1)
    model.Add(x12 + x16 == 1)
    x = {
        (0, "s1"): x01,
        (0, "s5"): x05,
        (1, "s2"): x12,
        (1, "s6"): x16,
    }
    spec = PairFreezeSpec(
        x=x,
        unit_list=[(0, _unit(1, "u0")), (1, _unit(1, "u1"))],
        feasible_slots_by_unit={0: [s1, s5], 1: [s2, s6]},
    )
    added = _freeze_good_doubles(
        model,
        _FixedSolver({x01: 1, x05: 0, x12: 1, x16: 0}),
        spec,
    )
    assert added == 2
    model.Minimize(x01 * 10 + x12 * 10 + x05 * 1 + x16 * 1)
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    status = solver.Solve(model)
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    assert solver.Value(x01) == 1
    assert solver.Value(x12) == 1


def test_freeze_good_doubles_hint_allows_moving_early_pair():
    pytest.importorskip("ortools")
    from ortools.sat.python import cp_model

    from app.domain.pair_epochs import PairFreezeSpec
    from app.domain.schedule_facts import SlotFact
    from app.services.schedule_solver import _freeze_good_doubles

    model = cp_model.CpModel()
    s1 = SlotFact(slot_id="s1", class_id=1, day=1, lesson=1, shift_id=1)
    s2 = SlotFact(slot_id="s2", class_id=1, day=1, lesson=2, shift_id=1)
    s5 = SlotFact(slot_id="s5", class_id=1, day=1, lesson=5, shift_id=1)
    s6 = SlotFact(slot_id="s6", class_id=1, day=1, lesson=6, shift_id=1)
    x01 = model.NewBoolVar("u0_s1")
    x05 = model.NewBoolVar("u0_s5")
    x12 = model.NewBoolVar("u1_s2")
    x16 = model.NewBoolVar("u1_s6")
    model.Add(x01 + x05 == 1)
    model.Add(x12 + x16 == 1)
    x = {
        (0, "s1"): x01,
        (0, "s5"): x05,
        (1, "s2"): x12,
        (1, "s6"): x16,
    }
    spec = PairFreezeSpec(
        x=x,
        unit_list=[(0, _unit(1, "u0")), (1, _unit(1, "u1"))],
        feasible_slots_by_unit={0: [s1, s5], 1: [s2, s6]},
        hard=False,
    )
    added = _freeze_good_doubles(
        model,
        _FixedSolver({x01: 1, x05: 0, x12: 1, x16: 0}),
        spec,
    )
    assert added == 2
    model.Minimize(x01 * 10 + x12 * 10 + x05 * 1 + x16 * 1)
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    status = solver.Solve(model)
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    assert solver.Value(x05) == 1
    assert solver.Value(x16) == 1


def test_staged_search_with_empty_pair_freeze_still_optimizes():
    pytest.importorskip("ortools")
    from ortools.sat.python import cp_model

    from app.domain.pair_epochs import PairFreezeSpec
    from app.services.schedule_solver import run_staged_cp_sat_search

    model = cp_model.CpModel()
    expensive = model.NewBoolVar("expensive")
    cheap = model.NewBoolVar("cheap")
    model.Add(expensive + cheap == 1)
    model.AddDecisionStrategy(
        [expensive, cheap],
        cp_model.CHOOSE_FIRST,
        cp_model.SELECT_MAX_VALUE,
    )
    cancelled, status, solver, _elapsed = run_staged_cp_sat_search(
        model,
        hint_maps=({"expensive": expensive, "cheap": cheap},),
        soft_stages=[(SOFT_STAGE_PACK_GAPS, [expensive * 10 + cheap * 1])],
        time_limit_sec=5.0,
        random_seed=1,
        num_workers=1,
        pair_freeze=PairFreezeSpec(x={}, unit_list=[], feasible_slots_by_unit={}),
    )
    assert cancelled is None
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    assert solver.Value(cheap) == 1


def test_deterrent_penalty_avoids_seventh_lessons_when_earlier_available():
    """Soft deterrent penalty ensures 7th lessons are avoided if 6th is possible."""
    pytest.importorskip("ortools")
    from ortools.sat.python import cp_model

    from app.domain.preferences import SOFT_STAGE_EARLY_ROOMS
    from app.services.schedule_solver import run_staged_cp_sat_search

    model = cp_model.CpModel()
    x_lesson7 = model.NewBoolVar("x_lesson7")
    x_lesson6 = model.NewBoolVar("x_lesson6")
    model.Add(x_lesson7 + x_lesson6 == 1)

    # Deterrent penalty on lesson 7
    cost_lesson7 = 10000 + 7
    cost_lesson6 = 6
    cancelled, status, solver, _elapsed = run_staged_cp_sat_search(
        model,
        hint_maps=({"x_lesson7": x_lesson7, "x_lesson6": x_lesson6},),
        soft_stages=[(SOFT_STAGE_EARLY_ROOMS, [x_lesson7 * cost_lesson7 + x_lesson6 * cost_lesson6])],
        time_limit_sec=5.0,
        random_seed=1,
        num_workers=1,
    )
    assert cancelled is None
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    assert solver.Value(x_lesson7) == 0
    assert solver.Value(x_lesson6) == 1



