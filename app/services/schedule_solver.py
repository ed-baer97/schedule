"""
Graph-based residual solver for schedule auto-fill.
CP-SAT global solver (one shift) with reassignment.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable

from app.domain.schedule_facts import SlotFact
from app.domain.schedule_rules import (
    classroom_at_capacity,
    occupancy_blocks_unit,
    subject_day_limit_reached,
    teacher_busy_at_slot,
    teacher_class_day_limit_reached,
    units_cannot_share_class_slot,
)
from app.models import Classroom, SchoolClass, TeachingAssignment
from app.services.assignment_hours import placed_counts, remaining_for
from app.services.classroom_resolver import load_settings
from app.services.schedule_fact_loader import (
    build_slots_by_class,
    build_unit_facts,
    load_cells_for_classes,
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


@dataclass
class FeasibleEdge:
    unit_id: str
    slot_id: str
    hard_ok: bool
    cost: int = 0


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
        max_per_subject_day,
        subject_day_counts,
        teacher_class_day_counts,
    ):
        adjacency = defaultdict(list)
        edges = []
        diagnostics_raw = defaultdict(Counter)
        feasible_by_assignment = Counter()

        for unit in units:
            assignment = assignment_map[unit.assignment_id]
            classroom_id = self._classroom_resolver(assignment, school_level)
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
                if reason is None and classroom_id:
                    cap = classroom_caps.get(classroom_id, 1)
                    if classroom_at_capacity(
                        slot, classroom_id, classroom_busy, cap
                    ):
                        reason = "Кабинет уже занят в это время"
                if reason is None:
                    subj_key = (unit.assignment_id, slot.day)
                    if subject_day_limit_reached(
                        subject_day_counts.get(subj_key, 0), max_per_subject_day
                    ):
                        reason = "Лимит уроков по предмету в этот день"
                if reason is None and unit.teacher_id:
                    tc_key = (unit.teacher_id, unit.class_id, slot.day)
                    if teacher_class_day_limit_reached(
                        teacher_class_day_counts.get(tc_key, 0), 2
                    ):
                        reason = "Лимит учитель+класс в этот день"
                if reason is not None:
                    diagnostics_raw[assignment.id][reason] += 1
                    continue
                edge = FeasibleEdge(
                    unit_id=unit.unit_id, slot_id=slot.slot_id, hard_ok=True, cost=0
                )
                edges.append(edge)
                adjacency[unit.unit_id].append(slot.slot_id)
                feasible_by_assignment[assignment.id] += 1

        return adjacency, edges, diagnostics_raw, feasible_by_assignment

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

    def solve_residuals(self, school_level="elementary", teacher_id=None, class_id=None, max_diag_items=20):
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

        teacher_ids = {u.teacher_id for u in units if u.teacher_id}
        classroom_ids = set()
        classroom_caps: dict[int, int] = {}
        for a in assignments:
            rid = self._classroom_resolver(a, school_level)
            if rid:
                classroom_ids.add(rid)
        for rid in classroom_ids:
            room = self.session.get(Classroom, rid)
            classroom_caps[rid] = (room.classes_capacity or 1) if room else 1

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

        adjacency, _edges, diagnostics_raw, feasible_by_assignment = self._build_edges(
            units,
            slots_by_class,
            assignment_map,
            school_level,
            teacher_busy=teacher_busy,
            classroom_busy=classroom_busy,
            class_occupancy=class_occupancy,
            classroom_caps=classroom_caps,
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
            unit = unit_map[unit_id]
            slot = slot_map[slot_id]
            assignment = assignment_map[unit.assignment_id]
            classroom_id = self._classroom_resolver(assignment, school_level)
            errors = self.validator.validate_cell(
                assignment=assignment,
                day=slot.day,
                lesson=slot.lesson,
                classroom_id=classroom_id,
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

    status: str  # OPTIMAL, FEASIBLE, INFEASIBLE, UNKNOWN, MODEL_INVALID, ERROR
    solver_status: str | None = None
    objective: int | None = None
    wall_time_sec: float | None = None
    placed_count: int = 0
    placements: list = field(default_factory=list)
    diagnostics: list = field(default_factory=list)
    metrics_before: dict[str, Any] | None = None
    metrics_after: dict[str, Any] | None = None
    error_message: str | None = None


class CpSatScheduleSolver:
    """
    CP-SAT solver for a single shift: rebuilds all cells for classes in the shift
    (clear + re-place) with hard constraints aligned to ScheduleValidator rules.
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


    def _compute_schedule_metrics(self, class_ids: list[int]) -> dict[str, Any]:
        """Aggregate window gaps and simple class load balance for classes in scope."""
        if not class_ids:
            return {
                "teacher_window_gaps": 0,
                "class_load_penalty": 0,
                "teachers_count": 0,
            }

        teacher_ids = (
            self.session.query(TeachingAssignment.teacher_id)
            .filter(
                TeachingAssignment.class_id.in_(class_ids),
                TeachingAssignment.teacher_id.isnot(None),
            )
            .distinct()
            .all()
        )
        teacher_ids = [t[0] for t in teacher_ids]

        wd = 5
        for cid in class_ids:
            sc = self.session.get(SchoolClass, cid)
            sh = sc.shift if sc and sc.shift_id else None
            if sh:
                wd = max(wd, sh.working_days)

        total_gaps = 0
        for tid in teacher_ids:
            total_gaps += len(self.validator.get_teacher_windows(tid, working_days=wd))

        load_penalty = 0
        cells = load_cells_for_classes(self.session, class_ids)
        by_class_day: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
        for cell in cells:
            by_class_day[cell.class_id][cell.day_of_week] += 1
        for cid in class_ids:
            by_day = by_class_day.get(cid) or {}
            if not by_day:
                continue
            vals = list(by_day.values())
            mean = sum(vals) / len(vals)
            for v in vals:
                load_penalty += int(abs(v - mean) * 10)

        return {
            "teacher_window_gaps": total_gaps,
            "class_load_penalty": load_penalty,
            "teachers_count": len(teacher_ids),
        }

    def solve_shift(
        self,
        shift_id: int,
        school_level: str,
        time_limit_sec: float = 60.0,
        random_seed: int = 1,
        max_diag_items: int = 20,
    ) -> CpSatSolveResult:
        """
        Rebuild schedule for all classes in the given shift (same school_level).
        Deletes existing cells for those classes and writes new ones if feasible.
        """
        if cp_model is None:
            return CpSatSolveResult(
                status="ERROR",
                error_message="Пакет ortools не установлен. Выполните: pip install ortools",
            )

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
        if not shift_classes:
            return CpSatSolveResult(
                status="MODEL_INVALID",
                diagnostics=[{"reason": "Нет классов для этой смены и уровня школы"}],
            )

        class_ids = [c.id for c in shift_classes]
        settings = load_settings(self.session, self.school_id, school_level)
        max_per_subject_day = settings.max_lessons_per_subject_per_day if settings else 2

        assignments = (
            self.session.query(TeachingAssignment).filter(
                TeachingAssignment.class_id.in_(class_ids),
                TeachingAssignment.teacher_id.isnot(None),
                TeachingAssignment.hours_per_week > 0,
                TeachingAssignment.school_id == self.school_id,
            )
            .all()
        )
        assignment_map = {a.id: a for a in assignments}

        if not assignments:
            return CpSatSolveResult(
                status="MODEL_INVALID",
                diagnostics=[{"reason": "Нет назначений с учителем для классов смены"}],
            )

        metrics_before = self._compute_schedule_metrics(class_ids)

        units = build_unit_facts(assignments, hours_mode="full")
        if not units:
            return CpSatSolveResult(status="MODEL_INVALID", diagnostics=[{"reason": "Нет часов для размещения"}])

        slots_by_class: dict[int, list[SlotFact]] = build_slots_by_class(
            shift_classes, session=self.session, with_intervals=True
        )

        shift_obj = shift_classes[0].shift
        if not shift_obj:
            return CpSatSolveResult(status="MODEL_INVALID", diagnostics=[{"reason": "Смена не найдена"}])

        # --- feasibility: enough slots per class
        for a in assignments:
            n_slots = len(slots_by_class.get(a.class_id, []))
            if a.hours_per_week > n_slots:
                return CpSatSolveResult(
                    status="INFEASIBLE",
                    diagnostics=[
                        {
                            "reason": (
                                f"Назначение {a.id}: требуется {a.hours_per_week} ч/н, "
                                f"слотов в сетке класса только {n_slots}"
                            )
                        }
                    ],
                )

        teacher_ids_scope = {u.teacher_id for u in units if u.teacher_id}
        external_busy = load_external_teacher_busy(
            self.session, teacher_ids_scope, class_ids
        )

        # --- CP-SAT model
        model = cp_model.CpModel()
        x: dict[tuple[int, str], cp_model.IntVar] = {}

        unit_list = list(enumerate(units))
        unit_by_idx = {i: u for i, u in unit_list}

        feasible_slots_by_unit: dict[int, list[SlotFact]] = {}
        for ui, unit in unit_list:
            slot_list = slots_by_class.get(unit.class_id, [])
            if not slot_list:
                return CpSatSolveResult(
                    status="INFEASIBLE",
                    diagnostics=[{"reason": f"Нет слотов для класса {unit.class_id}"}],
                )
            feasible = [
                s
                for s in slot_list
                if not teacher_busy_at_slot(s, unit.teacher_id, external_busy)
            ]
            if not feasible:
                return CpSatSolveResult(
                    status="INFEASIBLE",
                    diagnostics=[
                        {
                            "reason": (
                                f"Нет свободных слотов для часа {unit.unit_id} "
                                f"(учитель занят вне этой смены во всех пересечениях по времени)"
                            )
                        }
                    ],
                )
            feasible_slots_by_unit[ui] = feasible
            for slot in feasible:
                x[(ui, slot.slot_id)] = model.NewBoolVar(f"u{ui}_{slot.slot_id}")

        for ui, unit in unit_list:
            feas = feasible_slots_by_unit[ui]
            model.AddExactlyOne([x[(ui, s.slot_id)] for s in feas])

        # Same class slot: conflicting pairs cannot share slot
        by_class: dict[int, list[int]] = defaultdict(list)
        for ui, unit in unit_list:
            by_class[unit.class_id].append(ui)

        for cid, idxs in by_class.items():
            slot_list = slots_by_class[cid]
            for i_a in range(len(idxs)):
                for i_b in range(i_a + 1, len(idxs)):
                    uia, uib = idxs[i_a], idxs[i_b]
                    if not units_cannot_share_class_slot(
                        unit_by_idx[uia], unit_by_idx[uib]
                    ):
                        continue
                    for slot in slot_list:
                        key_a = (uia, slot.slot_id)
                        key_b = (uib, slot.slot_id)
                        if key_a not in x or key_b not in x:
                            continue
                        model.Add(x[key_a] + x[key_b] <= 1)

        # No class windows (hard):
        # within a day, lessons must form a contiguous prefix by lesson number.
        for cid in class_ids:
            uidxs = [ui for ui, u in unit_list if u.class_id == cid]
            if not uidxs:
                continue
            for day in range(1, shift_obj.working_days + 1):
                occ_by_lesson = {}
                lesson_start = shift_obj.start_lesson
                lesson_end = shift_obj.start_lesson + shift_obj.lessons_count
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

                # Prefix rule: if lesson N is occupied, N-1 must also be occupied.
                for lesson in range(lesson_start + 1, lesson_end):
                    model.Add(occ_by_lesson[lesson] <= occ_by_lesson[lesson - 1])

        # Teacher: at most one overlapping lesson across all classes in this shift
        by_teacher: dict[int, list[int]] = defaultdict(list)
        for ui, unit in unit_list:
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

        # Classroom: respect capacity for overlapping time (interval sweep)
        for room_id in {self._classroom_resolver(a, school_level) for a in assignments}:
            if not room_id:
                continue
            cap = self.session.get(Classroom, room_id)
            cap_n = (cap.classes_capacity or 1) if cap else 1
            if cap_n >= 10**5:
                continue
            items = []
            for ui, unit in unit_list:
                a = assignment_map[unit.assignment_id]
                if self._classroom_resolver(a, school_level) != room_id:
                    continue
                for slot in feasible_slots_by_unit[ui]:
                    key = (ui, slot.slot_id)
                    if key in x:
                        items.append((x[key], slot))
            _add_capacity_overlap_constraints(model, items, capacity=cap_n)

        # Max lessons per subject per day (per assignment)
        for a in assignments:
            uidxs = [ui for ui, u in unit_list if u.assignment_id == a.id]
            for day in range(1, shift_obj.working_days + 1):
                terms = []
                for ui in uidxs:
                    for slot in feasible_slots_by_unit[ui]:
                        if slot.day == day:
                            key = (ui, slot.slot_id)
                            if key in x:
                                terms.append(x[key])
                if terms:
                    model.Add(sum(terms) <= max_per_subject_day)

        # Subgroup pair synchronization (hard):
        # for the same class+subject with different group_number, lessons must be parallel.
        subgroup_pairs = []
        by_class_subject: dict[tuple[int, int], list[TeachingAssignment]] = defaultdict(list)
        for a in assignments:
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
            uidxs1 = [ui for ui, u in unit_list if u.assignment_id == a1.id]
            uidxs2 = [ui for ui, u in unit_list if u.assignment_id == a2.id]
            if not uidxs1 or not uidxs2:
                continue
            for day in range(1, shift_obj.working_days + 1):
                for lesson in range(shift_obj.start_lesson, shift_obj.start_lesson + shift_obj.lessons_count):
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

        # Max 2 lessons per day per teacher per class (across all subjects for that class)
        teacher_class_days: set[tuple[int, int]] = set()
        for a in assignments:
            if a.teacher_id:
                teacher_class_days.add((a.teacher_id, a.class_id))
        for tid, cid in teacher_class_days:
            for day in range(1, shift_obj.working_days + 1):
                terms = []
                for ui, unit in unit_list:
                    if unit.teacher_id != tid or unit.class_id != cid:
                        continue
                    for slot in feasible_slots_by_unit[ui]:
                        if slot.day == day:
                            key = (ui, slot.slot_id)
                            if key in x:
                                terms.append(x[key])
                if terms:
                    model.Add(sum(terms) <= 2)

        # Objective: prefer earlier days/lessons + soft balance + quality preferences
        from app.domain.preferences import solver_scales, weights_from_settings

        scales = solver_scales(weights_from_settings(settings))
        obj_terms = []
        w_slot = scales.slot
        w_balance = scales.day_balance
        w_non_adjacent_pair = scales.non_adjacent_pair
        w_subgroup_spread = scales.subgroup_spread
        for ui, unit in unit_list:
            for slot in feasible_slots_by_unit[ui]:
                key = (ui, slot.slot_id)
                if key not in x:
                    continue
                weight = slot.day * 100 + slot.lesson
                if slot.lesson >= 6:
                    weight += scales.late_lesson * (slot.lesson - 5)
                obj_terms.append(x[key] * weight * w_slot)

        # Penalize uneven distribution across days per class (linear proxy)
        for cid in class_ids:
            uidxs = [ui for ui, u in unit_list if u.class_id == cid]
            if not uidxs:
                continue
            for day in range(1, shift_obj.working_days + 1):
                day_terms = []
                for ui in uidxs:
                    for slot in feasible_slots_by_unit[ui]:
                        if slot.day == day:
                            key = (ui, slot.slot_id)
                            if key in x:
                                day_terms.append(x[key])
                if day_terms:
                    dsum = sum(day_terms)
                    for day2 in range(day + 1, shift_obj.working_days + 1):
                        day2_terms = []
                        for ui in uidxs:
                            for slot in feasible_slots_by_unit[ui]:
                                if slot.day == day2:
                                    key = (ui, slot.slot_id)
                                    if key in x:
                                        day2_terms.append(x[key])
                        if day2_terms:
                            diff = model.NewIntVar(-len(uidxs), len(uidxs), f"diff_{cid}_{day}_{day2}")
                            model.Add(diff == dsum - sum(day2_terms))
                            abs_diff = model.NewIntVar(0, len(uidxs), f"abs_{cid}_{day}_{day2}")
                            model.AddAbsEquality(abs_diff, diff)
                            obj_terms.append(abs_diff * w_balance)

        # Prefer 2 lessons per teacher+class per day to be adjacent.
        for tid, cid in teacher_class_days:
            for day in range(1, shift_obj.working_days + 1):
                lesson_occupied = {}
                for lesson in range(shift_obj.start_lesson, shift_obj.start_lesson + shift_obj.lessons_count):
                    terms = []
                    for ui, unit in unit_list:
                        if unit.teacher_id != tid or unit.class_id != cid:
                            continue
                        for slot in feasible_slots_by_unit[ui]:
                            if slot.day == day and slot.lesson == lesson:
                                key = (ui, slot.slot_id)
                                if key in x:
                                    terms.append(x[key])
                    occ = model.NewBoolVar(f"occ_t{tid}_c{cid}_d{day}_l{lesson}")
                    if terms:
                        model.Add(occ == sum(terms))
                    else:
                        model.Add(occ == 0)
                    lesson_occupied[lesson] = occ

                day_count = model.NewIntVar(0, 2, f"daycnt_t{tid}_c{cid}_d{day}")
                model.Add(day_count == sum(lesson_occupied.values()))

                is_two = model.NewBoolVar(f"is_two_t{tid}_c{cid}_d{day}")
                model.Add(day_count == 2).OnlyEnforceIf(is_two)
                model.Add(day_count != 2).OnlyEnforceIf(is_two.Not())

                adjacent_bools = []
                for lesson in range(shift_obj.start_lesson, shift_obj.start_lesson + shift_obj.lessons_count - 1):
                    b = model.NewBoolVar(f"adj_t{tid}_c{cid}_d{day}_l{lesson}")
                    l1 = lesson_occupied[lesson]
                    l2 = lesson_occupied[lesson + 1]
                    model.Add(b <= l1)
                    model.Add(b <= l2)
                    model.Add(b >= l1 + l2 - 1)
                    adjacent_bools.append(b)

                has_adjacent = model.NewBoolVar(f"has_adj_t{tid}_c{cid}_d{day}")
                if adjacent_bools:
                    model.Add(has_adjacent <= sum(adjacent_bools))
                    for b in adjacent_bools:
                        model.Add(has_adjacent >= b)
                else:
                    model.Add(has_adjacent == 0)

                non_adjacent_two = model.NewBoolVar(f"non_adj2_t{tid}_c{cid}_d{day}")
                model.Add(non_adjacent_two >= is_two - has_adjacent)
                model.Add(non_adjacent_two <= is_two)
                model.Add(non_adjacent_two <= 1 - has_adjacent)
                obj_terms.append(non_adjacent_two * w_non_adjacent_pair)

        # Subgroup subjects: prefer concentrating lessons in fewer days.
        subgroup_assignments = [a for a in assignments if a.group_number is not None]
        for a in subgroup_assignments:
            uidxs = [ui for ui, u in unit_list if u.assignment_id == a.id]
            for day in range(1, shift_obj.working_days + 1):
                day_terms = []
                for ui in uidxs:
                    for slot in feasible_slots_by_unit[ui]:
                        if slot.day == day:
                            key = (ui, slot.slot_id)
                            if key in x:
                                day_terms.append(x[key])
                day_active = model.NewBoolVar(f"subgrp_a{a.id}_d{day}")
                if day_terms:
                    dsum = sum(day_terms)
                    model.Add(dsum >= day_active)
                    model.Add(dsum <= a.hours_per_week * day_active)
                else:
                    model.Add(day_active == 0)
                obj_terms.append(day_active * w_subgroup_spread)

        if scales.teacher_days:
            teacher_ids = {unit.teacher_id for _, unit in unit_list if unit.teacher_id}
            for tid in teacher_ids:
                for day in range(1, shift_obj.working_days + 1):
                    day_terms = []
                    for ui, unit in unit_list:
                        if unit.teacher_id != tid:
                            continue
                        for slot in feasible_slots_by_unit[ui]:
                            if slot.day == day:
                                key = (ui, slot.slot_id)
                                if key in x:
                                    day_terms.append(x[key])
                    day_active = model.NewBoolVar(f"tdays_t{tid}_d{day}")
                    if day_terms:
                        dsum = sum(day_terms)
                        model.Add(dsum >= day_active)
                        model.Add(dsum <= len(day_terms) * day_active)
                    else:
                        model.Add(day_active == 0)
                    obj_terms.append(day_active * scales.teacher_days)

        model.Minimize(sum(obj_terms))

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(time_limit_sec)
        solver.parameters.num_search_workers = 8
        solver.parameters.random_seed = random_seed

        status = solver.Solve(model)

        status_name = solver.StatusName(status)
        if status in (cp_model.INFEASIBLE, cp_model.MODEL_INVALID):
            diag = [
                {
                    "reason": (
                        "CP-SAT: модель неразрешима при заданных ограничениях "
                        f"(статус {status_name}). Проверьте часы, смену и кабинеты."
                    )
                }
            ]
            return CpSatSolveResult(
                status="INFEASIBLE",
                solver_status=status_name,
                wall_time_sec=solver.WallTime(),
                diagnostics=diag[:max_diag_items],
                metrics_before=metrics_before,
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
                wall_time_sec=solver.WallTime(),
                diagnostics=diag[:max_diag_items],
                metrics_before=metrics_before,
            )

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return CpSatSolveResult(
                status="ERROR",
                solver_status=status_name,
                error_message=f"Неожиданный статус решателя: {status_name}",
                metrics_before=metrics_before,
            )

        # Apply: transaction — remove old cells for scope, insert new
        try:
            self._schedule.delete_cells(class_ids=class_ids, commit=False)

            placements = []
            for ui, unit in unit_list:
                a = assignment_map[unit.assignment_id]
                classroom_id = self._classroom_resolver(a, school_level)
                chosen = None
                for slot in feasible_slots_by_unit[ui]:
                    key = (ui, slot.slot_id)
                    if key not in x:
                        continue
                    if solver.Value(x[key]) == 1:
                        chosen = slot
                        break
                if not chosen:
                    self.session.rollback()
                    return CpSatSolveResult(
                        status="ERROR",
                        error_message="Решение не удалось извлечь (нет выбранного слота)",
                        metrics_before=metrics_before,
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
                metrics_before=metrics_before,
            )

        metrics_after = self._compute_schedule_metrics(class_ids)
        objective_val = int(solver.ObjectiveValue()) if solver.ObjectiveValue() is not None else None

        return CpSatSolveResult(
            status="OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE",
            solver_status=status_name,
            objective=objective_val,
            wall_time_sec=solver.WallTime(),
            placed_count=len(placements),
            placements=placements,
            diagnostics=[],
            metrics_before=metrics_before,
            metrics_after=metrics_after,
        )
