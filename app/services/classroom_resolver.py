"""Classroom resolution and missing-room warnings (shared by grid / auto / solvers)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.domain.classroom_rules import (
    ClassroomFact,
    PlacementContext,
    candidate_rooms_for,
)
from app.domain.schedule_facts import SlotFact
from app.domain.schedule_rules import classroom_at_capacity
from app.models import (
    Classroom,
    ScheduleCell,
    ScheduleSettings,
    SchoolClass,
    Subject,
    Teacher,
    TeachingAssignment,
)
from app.services.schedule_fact_loader import load_classroom_busy


def load_settings(
    db: Session, school_id: int, school_level: str
) -> ScheduleSettings | None:
    return db.scalars(
        select(ScheduleSettings).where(
            ScheduleSettings.school_level == school_level,
            ScheduleSettings.school_id == school_id,
        )
    ).first()


def classroom_fact(room: Classroom) -> ClassroomFact:
    return ClassroomFact(
        id=room.id,
        subject_id=room.subject_id,
        is_exclusive=bool(room.is_exclusive),
        classes_capacity=room.classes_capacity or 1,
    )


def load_classroom_facts(db: Session, school_id: int) -> list[ClassroomFact]:
    rooms = list(
        db.scalars(
            select(Classroom).where(Classroom.school_id == school_id)
        ).all()
    )
    return [classroom_fact(r) for r in rooms]


def placement_context_for(
    assignment: TeachingAssignment,
    settings: ScheduleSettings | None,
) -> PlacementContext | None:
    subject = assignment.subject
    if subject is None:
        return None
    teacher = assignment.teacher
    school_class = assignment.school_class
    mode = settings.classroom_mode if settings else "class_room"
    leave = bool(
        settings
        and settings.elementary_group_subjects_leave
        and getattr(school_class, "school_level", None) == "elementary"
        and assignment.group_number is not None
        and not subject.requires_fixed_classroom
    )
    return PlacementContext(
        subject_id=subject.id,
        requires_fixed_classroom=bool(subject.requires_fixed_classroom),
        teacher_home_classroom_id=teacher.home_classroom_id if teacher else None,
        preferred_classroom_id=assignment.preferred_classroom_id,
        class_home_classroom_id=(
            school_class.home_classroom_id if school_class else None
        ),
        classroom_mode=mode,
        force_teacher_home=leave,
    )


def candidate_classrooms(
    assignment: TeachingAssignment,
    settings: ScheduleSettings | None,
    rooms: list[ClassroomFact],
) -> list[tuple[int, int]]:
    """ORM adapter: ranked (classroom_id, cost) via domain candidate_rooms_for."""
    ctx = placement_context_for(assignment, settings)
    if ctx is None:
        return []
    return candidate_rooms_for(rooms, ctx)


def pick_classroom(
    assignment: TeachingAssignment,
    settings: ScheduleSettings | None,
    rooms: list[ClassroomFact],
    *,
    day: int | None = None,
    lesson: int | None = None,
    classroom_busy: dict | None = None,
    exclude_cell_id: int | None = None,
) -> int | None:
    """Best free classroom for assignment (optionally at a slot)."""
    candidates = candidate_classrooms(assignment, settings, rooms)
    if not candidates:
        return None
    if day is None or lesson is None or classroom_busy is None:
        return candidates[0][0]

    slot = SlotFact(
        slot_id=f"{day}-{lesson}",
        class_id=assignment.class_id,
        day=day,
        lesson=lesson,
        shift_id=None,
        interval=None,
    )
    caps = {r.id: r.classes_capacity for r in rooms}
    for room_id, _cost in candidates:
        cap = caps.get(room_id, 1)
        busy = classroom_busy or {}
        if exclude_cell_id and room_id in busy:
            busy = {
                **busy,
                room_id: [
                    b for b in busy[room_id] if b.source_cell_id != exclude_cell_id
                ],
            }
        if not classroom_at_capacity(slot, room_id, busy, cap):
            return room_id
    return None


def pick_classroom_for(
    db: Session,
    school_id: int,
    assignment: TeachingAssignment,
    school_level: str,
    *,
    day: int,
    lesson: int,
    exclude_cell_id: int | None = None,
) -> int | None:
    settings = load_settings(db, school_id, school_level)
    rooms = load_classroom_facts(db, school_id)
    candidates = candidate_classrooms(assignment, settings, rooms)
    if not candidates:
        return None
    room_ids = {rid for rid, _ in candidates}
    busy = load_classroom_busy(db, room_ids)
    return pick_classroom(
        assignment,
        settings,
        rooms,
        day=day,
        lesson=lesson,
        classroom_busy=busy,
        exclude_cell_id=exclude_cell_id,
    )


def get_classroom_warnings(
    db: Session, school_id: int, school_level: str | None = None
) -> list[tuple[str, str, object]]:
    """
    Warnings about lessons/entities without a classroom binding.
    Returns: [(type, message, cell_or_entity), ...]
    """
    warnings: list[tuple[str, str, object]] = []
    seen: set[tuple] = set()
    rooms = load_classroom_facts(db, school_id)

    if school_level:
        settings = load_settings(db, school_id, school_level)
        mode = settings.classroom_mode if settings else "class_room"
    else:
        settings = None
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
        if s.requires_fixed_classroom:
            pool = [r for r in rooms if r.subject_id == s.id]
            if not pool and not a.preferred_classroom_id:
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
            )
        ).all()
    )
    for s in subjects:
        pool = [r for r in rooms if r.subject_id == s.id]
        if pool:
            continue
        needs = db.scalars(
            select(TeachingAssignment.id).where(
                TeachingAssignment.subject_id == s.id,
                TeachingAssignment.preferred_classroom_id.is_(None),
            ).limit(1)
        ).first()
        if needs:
            key = ("fixed_subject_pool", s.id)
            if key not in seen:
                seen.add(key)
                warnings.append(
                    (
                        "fixed_subject_pool",
                        f'Предмет "{s.name}" требует кабинет, но ни один кабинет не привязан',
                        s,
                    )
                )

    return warnings
