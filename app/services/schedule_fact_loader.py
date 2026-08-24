"""
Load flat SlotFact / UnitFact / BusySlotFact from ORM for solvers and shared predicates.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Literal

from sqlalchemy.orm import Session, joinedload

from app.domain.schedule_facts import BusySlotFact, SlotFact, UnitFact
from app.models import ScheduleCell, SchoolClass, ShiftLessonTime, TeachingAssignment
from app.services.assignment_hours import remaining_for
from app.services.bell_schedule import get_interval_for_slot


def unit_fact_from_assignment(
    assignment: TeachingAssignment,
    *,
    hour_index: int,
) -> UnitFact:
    level = (
        assignment.school_class.school_level
        if assignment.school_class
        else "elementary"
    )
    return UnitFact(
        unit_id=f"a{assignment.id}#{hour_index}",
        assignment_id=assignment.id,
        teacher_id=assignment.teacher_id,
        class_id=assignment.class_id,
        subject_id=assignment.subject_id,
        group_number=assignment.group_number,
        school_level=level,
    )


def candidate_unit_fact(assignment: TeachingAssignment) -> UnitFact:
    """UnitFact for a single placement check (validator / edge build)."""
    return unit_fact_from_assignment(assignment, hour_index=0)


def build_unit_facts(
    assignments: Iterable[TeachingAssignment],
    *,
    hours_mode: Literal["full", "remaining"] = "full",
    placed_counts: dict[int, int] | None = None,
) -> list[UnitFact]:
    """
    Expand assignments into hour units.
    ``full`` — hours_per_week units (CP-SAT rebuild).
    ``remaining`` — only unplaced hours (residual matching).
    """
    units: list[UnitFact] = []
    placed = placed_counts or {}
    for assignment in assignments:
        if hours_mode == "remaining":
            n = remaining_for(assignment, placed=placed.get(assignment.id, 0))
        else:
            n = int(assignment.hours_per_week or 0)
        for i in range(n):
            units.append(unit_fact_from_assignment(assignment, hour_index=i + 1))
    return units


def _interval_cache_for_shifts(
    session: Session, shift_ids: set[int]
) -> dict[tuple[int, int, int], tuple]:
    """Preload ShiftLessonTime rows: (shift_id, day, lesson) -> (start, end)."""
    cache: dict[tuple[int, int, int], tuple] = {}
    if not shift_ids:
        return cache
    rows = (
        session.query(ShiftLessonTime)
        .filter(ShiftLessonTime.shift_id.in_(shift_ids))
        .all()
    )
    for row in rows:
        cache[(row.shift_id, row.day_of_week, row.lesson_number)] = (
            row.time_start,
            row.time_end,
        )
    return cache


def _interval_for(
    shift_id: int | None,
    lesson: int,
    day: int,
    *,
    session: Session,
    lesson_time_cache: dict[tuple[int, int, int], tuple] | None = None,
):
    if not shift_id:
        return None
    if lesson_time_cache is not None and lesson != 0:
        cached = lesson_time_cache.get((shift_id, day, lesson))
        if cached is not None:
            return cached
        # Miss: may be class hour or missing row — fall through
        if lesson != 0:
            return None
    return get_interval_for_slot(shift_id, lesson, day, session=session)


def build_slot_facts_for_class(
    school_class: SchoolClass,
    *,
    session: Session | None = None,
    with_intervals: bool = False,
    allow_default_grid: bool = False,
    lesson_time_cache: dict[tuple[int, int, int], tuple] | None = None,
) -> list[SlotFact]:
    """
    Grid slots for one class from its shift.
    Without a shift: empty list, unless ``allow_default_grid`` (legacy residual fallback).
    """
    shift = school_class.shift if school_class and school_class.shift_id else None
    if not shift and not allow_default_grid:
        return []
    if shift:
        wd = shift.working_days
        start = shift.start_lesson
        end_excl = shift.start_lesson + shift.lessons_count
        shift_id = school_class.shift_id
    else:
        wd, start, end_excl, shift_id = 5, 1, 8, None
    slots: list[SlotFact] = []
    for day in range(1, wd + 1):
        for lesson in range(start, end_excl):
            interval = None
            if with_intervals and session is not None and shift_id:
                interval = _interval_for(
                    shift_id,
                    lesson,
                    day,
                    session=session,
                    lesson_time_cache=lesson_time_cache,
                )
            slots.append(
                SlotFact(
                    slot_id=f"c{school_class.id}:d{day}:l{lesson}",
                    class_id=school_class.id,
                    day=day,
                    lesson=lesson,
                    shift_id=shift_id,
                    interval=interval,
                )
            )
    return slots


def build_slots_by_class(
    classes: Iterable[SchoolClass],
    *,
    session: Session | None = None,
    with_intervals: bool = False,
    allow_default_grid: bool = False,
) -> dict[int, list[SlotFact]]:
    class_list = list(classes)
    lesson_time_cache = None
    if with_intervals and session is not None:
        shift_ids = {
            sc.shift_id for sc in class_list if sc.shift_id is not None
        }
        lesson_time_cache = _interval_cache_for_shifts(session, shift_ids)
    return {
        sc.id: build_slot_facts_for_class(
            sc,
            session=session,
            with_intervals=with_intervals,
            allow_default_grid=allow_default_grid,
            lesson_time_cache=lesson_time_cache,
        )
        for sc in class_list
    }


def occupancy_fact_from_cell(
    cell: ScheduleCell,
    session: Session,
    *,
    lesson_time_cache: dict[tuple[int, int, int], tuple] | None = None,
) -> BusySlotFact:
    sc = cell.school_class
    shift_id = sc.shift_id if sc else None
    interval = _interval_for(
        shift_id,
        cell.lesson_number,
        cell.day_of_week,
        session=session,
        lesson_time_cache=lesson_time_cache,
    )
    asg = cell.assignment
    return BusySlotFact(
        shift_id=shift_id,
        day=cell.day_of_week,
        lesson=cell.lesson_number,
        interval=interval,
        assignment_id=cell.assignment_id,
        subject_id=asg.subject_id if asg else None,
        group_number=asg.group_number if asg else None,
        class_id=cell.class_id,
        classroom_id=cell.classroom_id,
        source_cell_id=cell.id,
    )


def _busy_query(session: Session):
    return (
        session.query(ScheduleCell)
        .options(
            joinedload(ScheduleCell.school_class),
            joinedload(ScheduleCell.assignment),
        )
    )


def load_teacher_busy(
    session: Session,
    teacher_ids: set[int],
    *,
    exclude_cell_id: int | None = None,
    class_ids_scope: list[int] | None = None,
    outside_scope_only: bool = False,
) -> dict[int, list[BusySlotFact]]:
    """
    Teacher occupancy with bell intervals.
    ``outside_scope_only`` — only cells whose class_id is outside ``class_ids_scope``
    (CP-SAT external busy). Otherwise all matching teacher cells (residual/validator).
    """
    busy: dict[int, list[BusySlotFact]] = defaultdict(list)
    if not teacher_ids:
        return busy
    q = (
        _busy_query(session)
        .join(TeachingAssignment)
        .filter(TeachingAssignment.teacher_id.in_(teacher_ids))
    )
    if exclude_cell_id is not None:
        q = q.filter(ScheduleCell.id != exclude_cell_id)
    if outside_scope_only:
        if not class_ids_scope:
            return busy
        q = q.filter(~ScheduleCell.class_id.in_(class_ids_scope))

    rows = q.all()
    shift_ids = {
        (cell.school_class.shift_id if cell.school_class else None)
        for cell in rows
    }
    shift_ids.discard(None)
    lesson_time_cache = _interval_cache_for_shifts(session, shift_ids)  # type: ignore[arg-type]

    for cell in rows:
        tid = cell.assignment.teacher_id if cell.assignment else None
        if not tid:
            continue
        busy[tid].append(
            occupancy_fact_from_cell(
                cell, session, lesson_time_cache=lesson_time_cache
            )
        )
    return busy


def load_external_teacher_busy(
    session: Session,
    teacher_ids: set[int],
    class_ids_scope: list[int],
) -> dict[int, list[BusySlotFact]]:
    """Teacher occupancy outside the rebuild scope (CP-SAT)."""
    return load_teacher_busy(
        session,
        teacher_ids,
        class_ids_scope=class_ids_scope,
        outside_scope_only=True,
    )


def load_classroom_busy(
    session: Session,
    classroom_ids: set[int],
    *,
    exclude_cell_id: int | None = None,
) -> dict[int, list[BusySlotFact]]:
    """Classroom occupancy with bell intervals."""
    busy: dict[int, list[BusySlotFact]] = defaultdict(list)
    if not classroom_ids:
        return busy
    q = _busy_query(session).filter(ScheduleCell.classroom_id.in_(classroom_ids))
    if exclude_cell_id is not None:
        q = q.filter(ScheduleCell.id != exclude_cell_id)
    rows = q.all()
    shift_ids = {
        (cell.school_class.shift_id if cell.school_class else None)
        for cell in rows
    }
    shift_ids.discard(None)
    lesson_time_cache = _interval_cache_for_shifts(session, shift_ids)  # type: ignore[arg-type]
    for cell in rows:
        if not cell.classroom_id:
            continue
        busy[cell.classroom_id].append(
            occupancy_fact_from_cell(
                cell, session, lesson_time_cache=lesson_time_cache
            )
        )
    return busy


def load_class_occupancy(
    session: Session,
    class_ids: list[int],
    *,
    exclude_cell_id: int | None = None,
) -> dict[int, list[BusySlotFact]]:
    """Existing class-grid occupancy keyed by class_id."""
    by_class: dict[int, list[BusySlotFact]] = defaultdict(list)
    if not class_ids:
        return by_class
    q = _busy_query(session).filter(ScheduleCell.class_id.in_(class_ids))
    if exclude_cell_id is not None:
        q = q.filter(ScheduleCell.id != exclude_cell_id)
    rows = q.all()
    shift_ids = {
        (cell.school_class.shift_id if cell.school_class else None)
        for cell in rows
    }
    shift_ids.discard(None)
    lesson_time_cache = _interval_cache_for_shifts(session, shift_ids)  # type: ignore[arg-type]
    for cell in rows:
        by_class[cell.class_id].append(
            occupancy_fact_from_cell(
                cell, session, lesson_time_cache=lesson_time_cache
            )
        )
    return by_class


def load_cells_for_classes(
    session: Session, class_ids: list[int]
) -> list[ScheduleCell]:
    """Schedule cells for class scope (metrics / diagnostics helpers)."""
    if not class_ids:
        return []
    return (
        _busy_query(session)
        .filter(ScheduleCell.class_id.in_(class_ids))
        .all()
    )


def candidate_slot_fact(
    session: Session,
    *,
    class_id: int,
    day: int,
    lesson: int,
    shift_id: int | None,
) -> SlotFact:
    """Build a candidate SlotFact with bell interval when available."""
    return SlotFact(
        slot_id=f"c{class_id}:d{day}:l{lesson}",
        class_id=class_id,
        day=day,
        lesson=lesson,
        shift_id=shift_id,
        interval=get_interval_for_slot(shift_id, lesson, day, session=session),
    )
