"""Shared ScheduleCell load options and DTO projections."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import ScheduleCell, Subject, TeachingAssignment

CELL_LOAD = (
    joinedload(ScheduleCell.assignment).joinedload(TeachingAssignment.subject),
    joinedload(ScheduleCell.assignment).joinedload(TeachingAssignment.teacher),
    joinedload(ScheduleCell.classroom),
)

CELL_LOAD_WITH_CLASS = (
    *CELL_LOAD,
    joinedload(ScheduleCell.school_class),
)


def reload_cell(db: Session, cell_id: int) -> ScheduleCell:
    return (
        db.execute(
            select(ScheduleCell).options(*CELL_LOAD).where(ScheduleCell.id == cell_id)
        )
        .scalars()
        .unique()
        .one()
    )


def load_cells(db: Session, *where, with_class: bool = False) -> list[ScheduleCell]:
    opts = CELL_LOAD_WITH_CLASS if with_class else CELL_LOAD
    stmt = select(ScheduleCell).options(*opts)
    for clause in where:
        stmt = stmt.where(clause)
    return list(db.execute(stmt).scalars().unique().all())


def _cell_projection(cell: ScheduleCell) -> dict:
    """Full cell projection; schedule/report views pick needed keys."""
    a = cell.assignment
    subj = a.subject if a else None
    teacher = a.teacher if a else None
    return {
        "id": cell.id,
        "class_id": cell.class_id,
        "day_of_week": cell.day_of_week,
        "lesson_number": cell.lesson_number,
        "assignment_id": cell.assignment_id,
        "classroom_id": cell.classroom_id,
        "subject_id": subj.id if subj else 0,
        "subject_name": subj.display_name if subj else "?",
        "subject_color": (subj.display_color if subj else Subject.DEFAULT_COLOR),
        "teacher_id": teacher.id if teacher else None,
        "teacher_name": teacher.display_name if teacher else None,
        "group_number": a.group_number if a else None,
        "classroom_name": cell.classroom.display_name if cell.classroom else None,
        "class_name": cell.school_class.name if cell.school_class else "?",
        "requires_subgroup": bool(getattr(subj, "requires_subgroup", False)),
    }


_SCHEDULE_KEYS = (
    "id",
    "class_id",
    "day_of_week",
    "lesson_number",
    "assignment_id",
    "classroom_id",
    "subject_id",
    "subject_name",
    "subject_color",
    "teacher_id",
    "teacher_name",
    "group_number",
    "classroom_name",
    "requires_subgroup",
)

_REPORT_KEYS = (
    "id",
    "day_of_week",
    "lesson_number",
    "subject_name",
    "subject_color",
    "teacher_name",
    "class_name",
    "classroom_name",
    "group_number",
)


def cell_to_schedule_dict(cell: ScheduleCell) -> dict:
    full = _cell_projection(cell)
    return {k: full[k] for k in _SCHEDULE_KEYS}


def cell_to_report_dict(cell: ScheduleCell) -> dict:
    full = _cell_projection(cell)
    return {k: full[k] for k in _REPORT_KEYS}
