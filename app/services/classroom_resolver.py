"""Classroom resolution and missing-room warnings (shared by grid / auto / solvers)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    ScheduleCell,
    ScheduleSettings,
    SchoolClass,
    Subject,
    Teacher,
    TeachingAssignment,
)


def load_settings(
    db: Session, school_id: int, school_level: str
) -> ScheduleSettings | None:
    return db.scalars(
        select(ScheduleSettings).where(
            ScheduleSettings.school_level == school_level,
            ScheduleSettings.school_id == school_id,
        )
    ).first()


def resolve_classroom(
    assignment: TeachingAssignment,
    school_level: str,
    settings: ScheduleSettings | None,
) -> int | None:
    """
    classroom_id for a schedule cell.
    Priority: fixed-subject room, elementary group leave, classroom_mode, preferred.
    """
    subject = assignment.subject
    teacher = assignment.teacher
    school_class = assignment.school_class

    if subject and subject.requires_fixed_classroom:
        return assignment.preferred_classroom_id or subject.default_classroom_id

    if (
        school_level == "elementary"
        and settings
        and settings.elementary_group_subjects_leave
        and assignment.group_number is not None
        and teacher
        and teacher.home_classroom_id
    ):
        return teacher.home_classroom_id

    mode = settings.classroom_mode if settings else "class_room"
    if mode == "teacher_room" and teacher:
        return teacher.home_classroom_id
    if mode == "class_room" and school_class:
        return school_class.home_classroom_id

    return assignment.preferred_classroom_id


def resolve_classroom_for(
    db: Session,
    school_id: int,
    assignment: TeachingAssignment,
    school_level: str,
) -> int | None:
    settings = load_settings(db, school_id, school_level)
    return resolve_classroom(assignment, school_level, settings)


def get_classroom_warnings(
    db: Session, school_id: int, school_level: str | None = None
) -> list[tuple[str, str, object]]:
    """
    Warnings about lessons/entities without a classroom binding.
    Returns: [(type, message, cell_or_entity), ...]
    """
    warnings: list[tuple[str, str, object]] = []
    seen: set[tuple] = set()

    if school_level:
        settings = load_settings(db, school_id, school_level)
        mode = settings.classroom_mode if settings else "class_room"
    else:
        mode = "class_room"

    cell_stmt = (
        select(ScheduleCell)
        .options(
            joinedload(ScheduleCell.assignment).joinedload(TeachingAssignment.subject),
            joinedload(ScheduleCell.assignment).joinedload(TeachingAssignment.teacher),
            joinedload(ScheduleCell.school_class),
        )
        .where(
            ScheduleCell.classroom_id.is_(None),
            ScheduleCell.school_id == school_id,
        )
    )
    if school_level:
        cell_stmt = cell_stmt.join(SchoolClass).where(
            SchoolClass.school_level == school_level
        )
    cells = list(db.execute(cell_stmt).scalars().unique().all())

    for cell in cells:
        a = cell.assignment
        s = a.subject if a else None
        if not a or not s:
            continue
        if s.requires_fixed_classroom and not (
            a.preferred_classroom_id or s.default_classroom_id
        ):
            key = ("fixed_no_room", cell.class_id, s.id)
            if key not in seen:
                seen.add(key)
                class_name = cell.school_class.name if cell.school_class else "?"
                warnings.append(
                    (
                        "fixed_no_room",
                        f"{class_name} {s.name}: предмет требует кабинет",
                        cell,
                    )
                )
        elif mode == "teacher_room" and a.teacher and not a.teacher.home_classroom_id:
            key = ("teacher_no_room", a.teacher_id)
            if key not in seen:
                seen.add(key)
                warnings.append(
                    (
                        "teacher_no_room",
                        f"{a.teacher.display_name} не имеет прикреплённого кабинета",
                        cell,
                    )
                )
        elif (
            mode == "class_room"
            and cell.school_class
            and not cell.school_class.home_classroom_id
        ):
            key = ("class_no_room", cell.class_id)
            if key not in seen:
                seen.add(key)
                warnings.append(
                    (
                        "class_no_room",
                        f"{cell.school_class.name} не имеет прикреплённого кабинета",
                        cell,
                    )
                )

    if school_level and mode == "teacher_room":
        tq = (
            select(Teacher)
            .join(TeachingAssignment)
            .join(SchoolClass)
            .where(
                SchoolClass.school_level == school_level,
                Teacher.home_classroom_id.is_(None),
                Teacher.school_id == school_id,
            )
            .distinct()
        )
        for t in db.scalars(tq).all():
            key = ("teacher_no_room", t.id)
            if key not in seen:
                seen.add(key)
                warnings.append(
                    (
                        "teacher_no_room",
                        f"Учитель {t.display_name} не имеет прикреплённого кабинета",
                        t,
                    )
                )

    if school_level and mode == "class_room":
        classes = list(
            db.scalars(
                select(SchoolClass).where(
                    SchoolClass.school_id == school_id,
                    SchoolClass.school_level == school_level,
                    SchoolClass.home_classroom_id.is_(None),
                )
            ).all()
        )
        for c in classes:
            has_teacher = db.scalars(
                select(TeachingAssignment.id).where(
                    TeachingAssignment.class_id == c.id,
                    TeachingAssignment.teacher_id.isnot(None),
                ).limit(1)
            ).first()
            if has_teacher:
                key = ("class_no_room", c.id)
                if key not in seen:
                    seen.add(key)
                    warnings.append(
                        (
                            "class_no_room",
                            f"Класс {c.name} не имеет прикреплённого кабинета",
                            c,
                        )
                    )

    subjects = list(
        db.scalars(
            select(Subject).where(
                Subject.school_id == school_id,
                Subject.requires_fixed_classroom.is_(True),
                Subject.default_classroom_id.is_(None),
            )
        ).all()
    )
    for s in subjects:
        needs = db.scalars(
            select(TeachingAssignment.id).where(
                TeachingAssignment.subject_id == s.id,
                TeachingAssignment.preferred_classroom_id.is_(None),
            ).limit(1)
        ).first()
        if needs:
            key = ("fixed_subject_default", s.id)
            if key not in seen:
                seen.add(key)
                warnings.append(
                    (
                        "fixed_subject_default",
                        f'Предмет "{s.name}" требует кабинет, но не указан кабинет по умолчанию',
                        s,
                    )
                )

    return warnings
