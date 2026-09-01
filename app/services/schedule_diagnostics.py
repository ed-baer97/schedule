"""Shared unplaced-hours diagnostics for auto / residual solver."""
from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import SchoolClass, TeachingAssignment
from app.domain.shift_grid import lesson_end_exclusive
from app.services.assignment_hours import placed_counts, remaining_for
from app.services.validators import ScheduleValidator


def build_unplaced_diagnostics(
    db: Session,
    school_id: int,
    *,
    school_level: str = "elementary",
    teacher_id: int | None = None,
    class_id: int | None = None,
    max_items: int = 20,
    classroom_id_for: Callable[[TeachingAssignment, str], int | None] | None = None,
    validator: ScheduleValidator | None = None,
) -> list[dict[str, Any]]:
    """
    For each assignment with remaining hours, count why slots fail validate_cell.
    """
    validator = validator or ScheduleValidator(db, school_id=school_id)
    stmt = (
        select(TeachingAssignment)
        .options(
            joinedload(TeachingAssignment.subject),
            joinedload(TeachingAssignment.teacher),
            joinedload(TeachingAssignment.school_class).joinedload(SchoolClass.shift),
        )
        .join(SchoolClass, SchoolClass.id == TeachingAssignment.class_id)
        .where(
            SchoolClass.school_level == school_level,
            TeachingAssignment.teacher_id.isnot(None),
            TeachingAssignment.school_id == school_id,
            SchoolClass.school_id == school_id,
        )
    )
    if teacher_id is not None:
        stmt = stmt.where(TeachingAssignment.teacher_id == teacher_id)
    if class_id is not None:
        stmt = stmt.where(TeachingAssignment.class_id == class_id)

    assignments = list(db.execute(stmt).scalars().unique().all())
    counts = placed_counts(db, [a.id for a in assignments])

    diagnostics: list[dict[str, Any]] = []
    for a in assignments:
        remaining = remaining_for(a, placed=counts.get(a.id, 0))
        if remaining <= 0:
            continue

        shift = a.school_class.shift if a.school_class and a.school_class.shift_id else None
        working_days = shift.working_days if shift else 5
        max_lessons = shift.max_lessons_per_day if shift else 7
        lesson_start = shift.start_lesson if shift else 1
        lesson_end_excl = (
            lesson_end_exclusive(shift) if shift else max_lessons + 1
        )

        reasons: Counter[str] = Counter()
        feasible_slots = 0
        checked_slots = 0

        for day in range(1, working_days + 1):
            day_end = lesson_end_exclusive(shift, day) if shift else lesson_end_excl
            for lesson in range(lesson_start, day_end):
                checked_slots += 1
                classroom_id = None
                if classroom_id_for:
                    try:
                        classroom_id = classroom_id_for(
                            a, school_level, day=day, lesson=lesson
                        )
                    except TypeError:
                        classroom_id = classroom_id_for(a, school_level)
                errors = validator.validate_cell(
                    assignment=a,
                    day=day,
                    lesson=lesson,
                    classroom_id=classroom_id,
                    require_classroom=True,
                )
                if not errors:
                    feasible_slots += 1
                    continue
                for err in errors:
                    reasons[err] += 1

        top_reasons = [
            {"reason": reason, "count": count}
            for reason, count in reasons.most_common(3)
        ]
        diagnostics.append(
            {
                "assignment_id": a.id,
                "class_name": a.school_class.name if a.school_class else "?",
                "subject_name": a.subject.display_name if a.subject else "?",
                "teacher_name": a.teacher.display_name if a.teacher else "?",
                "remaining_hours": remaining,
                "feasible_slots": feasible_slots,
                "checked_slots": checked_slots,
                "top_reasons": top_reasons,
            }
        )

    diagnostics.sort(
        key=lambda x: (
            -x["remaining_hours"],
            x["feasible_slots"],
            x["class_name"],
            x["subject_name"],
        )
    )
    return diagnostics[:max_items]
