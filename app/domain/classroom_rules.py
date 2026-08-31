"""Classroom suitability and placement cost (no Session)."""
from __future__ import annotations

from dataclasses import dataclass

# Soft costs for auto-scheduler / CP-SAT (lower = better).
COST_OWNER_SUBJECT = 0
COST_SAME_SUBJECT = 10
COST_OTHER_SUBJECT = 50
COST_GENERAL = 40
COST_PREFERRED_BONUS = -5

# Auto-scheduler hard rule: every placed lesson must have a concrete classroom.
MSG_NO_CLASSROOM = "Нет доступного кабинета для урока"


CLASSROOM_SCHOOL_LEVELS = frozenset({"elementary", "secondary"})


def normalize_classroom_school_level(value: str | None) -> str | None:
    if not value:
        return None
    v = str(value).strip()
    return v if v in CLASSROOM_SCHOOL_LEVELS else None


@dataclass(frozen=True)
class ClassroomFact:
    id: int
    subject_ids: frozenset[int] = frozenset()
    is_exclusive: bool = False
    classes_capacity: int = 1
    school_level: str | None = None


@dataclass(frozen=True)
class PlacementContext:
    """Facts needed to score a room for an assignment."""

    subject_id: int
    requires_fixed_classroom: bool
    teacher_home_classroom_id: int | None = None
    preferred_classroom_id: int | None = None
    class_home_classroom_id: int | None = None
    classroom_mode: str = "class_room"  # class_room | teacher_room
    class_school_level: str | None = None
    # Elementary subgroups leave the class room for the teacher's home.
    force_teacher_home: bool = False
    # Elementary non-fixed subjects stay in the class home room.
    force_class_home: bool = False


def room_has_subject(room: ClassroomFact, subject_id: int) -> bool:
    return subject_id in room.subject_ids


def room_allows_subject(
    room: ClassroomFact,
    *,
    subject_id: int,
    requires_fixed_classroom: bool,
) -> bool:
    """
    Hard rule: can this subject be placed in this classroom?

    - Fixed subject → only rooms tagged with that subject.
    - Exclusive room → only its tagged subjects.
    - Subject-tagged non-exclusive → any non-fixed subject.
    - Untagged (general) room → any non-fixed subject.
    """
    if requires_fixed_classroom:
        return room_has_subject(room, subject_id)

    if room.is_exclusive:
        return room_has_subject(room, subject_id)

    # Non-fixed subject: general rooms and non-exclusive subject rooms OK.
    return True


def room_allows_level(room: ClassroomFact, class_school_level: str | None) -> bool:
    """Hard: tagged rooms only for that school level. Untagged = shared (gym, lab)."""
    tagged = room.school_level
    if not tagged:
        return True
    if not class_school_level:
        return True
    return tagged == class_school_level


def room_allows(
    room: ClassroomFact,
    *,
    subject_id: int,
    requires_fixed_classroom: bool,
    class_school_level: str | None = None,
) -> bool:
    if not room_allows_level(room, class_school_level):
        return False
    return room_allows_subject(
        room,
        subject_id=subject_id,
        requires_fixed_classroom=requires_fixed_classroom,
    )


def room_denial_message(
    room: ClassroomFact,
    *,
    subject_id: int,
    subject_name: str,
    requires_fixed_classroom: bool,
    room_display_name: str,
    room_subject_name: str | None = None,
    class_school_level: str | None = None,
) -> str | None:
    """Human-readable reason if the room cannot host this lesson."""
    if room_allows(
        room,
        subject_id=subject_id,
        requires_fixed_classroom=requires_fixed_classroom,
        class_school_level=class_school_level,
    ):
        return None
    if not room_allows_level(room, class_school_level):
        if room.school_level == "elementary":
            return (
                f"Кабинет {room_display_name} — кабинет начальной школы, "
                "уроки основной школы сюда нельзя"
            )
        if room.school_level == "secondary":
            return (
                f"Кабинет {room_display_name} — кабинет основной школы, "
                "уроки начальной сюда нельзя"
            )
        return f"Кабинет {room_display_name} недоступен для этого уровня школы"
    if requires_fixed_classroom:
        return (
            f"Предмет «{subject_name}» требует фиксированный кабинет — "
            f"нельзя ставить в {room_display_name}"
        )
    if room.is_exclusive:
        subj = room_subject_name or "своих предметов"
        return f"Кабинет {room_display_name} только для {subj}"
    return f"Кабинет {room_display_name} недоступен для «{subject_name}»"


def placement_cost(
    room: ClassroomFact,
    ctx: PlacementContext,
) -> int | None:
    """
    Soft cost for placing ctx into room. None = forbidden.

    Priority (lower cost better):
    1. Teacher home + room is tagged with assignment subject → 0
    2. Same subject as room (other teacher) → low
    3. General (empty tags) / other non-exclusive subject room → medium
    """
    if not room_allows(
        room,
        subject_id=ctx.subject_id,
        requires_fixed_classroom=ctx.requires_fixed_classroom,
        class_school_level=ctx.class_school_level,
    ):
        return None

    if ctx.requires_fixed_classroom:
        cost = COST_SAME_SUBJECT
        if ctx.preferred_classroom_id == room.id:
            cost += COST_PREFERRED_BONUS
        if ctx.teacher_home_classroom_id == room.id:
            cost = COST_OWNER_SUBJECT
        return max(0, cost)

    # Non-fixed subject
    if room_has_subject(room, ctx.subject_id):
        if ctx.teacher_home_classroom_id == room.id:
            cost = COST_OWNER_SUBJECT
        else:
            cost = COST_SAME_SUBJECT
    elif not room.subject_ids:
        cost = COST_GENERAL
        # Prefer home room from classroom_mode when scoring general rooms
        if (
            ctx.classroom_mode == "teacher_room"
            and ctx.teacher_home_classroom_id == room.id
        ):
            cost = COST_OWNER_SUBJECT
        elif (
            ctx.classroom_mode == "class_room"
            and ctx.class_home_classroom_id == room.id
        ):
            cost = min(cost, 5)
    else:
        # Other subject's non-exclusive room
        cost = COST_OTHER_SUBJECT

    if ctx.preferred_classroom_id == room.id:
        cost = max(0, cost + COST_PREFERRED_BONUS)

    return cost


def rank_candidate_rooms(
    rooms: list[ClassroomFact],
    ctx: PlacementContext,
) -> list[tuple[int, int]]:
    """Return [(classroom_id, cost), ...] sorted by cost ascending."""
    scored: list[tuple[int, int]] = []
    for room in rooms:
        cost = placement_cost(room, ctx)
        if cost is not None:
            scored.append((room.id, cost))
    scored.sort(key=lambda x: (x[1], x[0]))
    return scored


def candidate_rooms_for(
    rooms: list[ClassroomFact],
    ctx: PlacementContext,
) -> list[tuple[int, int]]:
    """
    Ranked (classroom_id, cost) for ctx.

    force_teacher_home (non-fixed subjects): only the teacher's home room
    if it exists and allows the placement; otherwise fall through.
    force_class_home: only the class home room (elementary stay-in-class).
    """
    if (
        ctx.force_teacher_home
        and not ctx.requires_fixed_classroom
        and ctx.teacher_home_classroom_id is not None
    ):
        home = next(
            (r for r in rooms if r.id == ctx.teacher_home_classroom_id), None
        )
        if home is not None and room_allows(
            home,
            subject_id=ctx.subject_id,
            requires_fixed_classroom=False,
            class_school_level=ctx.class_school_level,
        ):
            return [(home.id, COST_OWNER_SUBJECT)]
    if (
        ctx.force_class_home
        and not ctx.requires_fixed_classroom
        and ctx.class_home_classroom_id is not None
    ):
        home = next(
            (r for r in rooms if r.id == ctx.class_home_classroom_id), None
        )
        if home is not None and room_allows(
            home,
            subject_id=ctx.subject_id,
            requires_fixed_classroom=False,
            class_school_level=ctx.class_school_level,
        ):
            return [(home.id, COST_OWNER_SUBJECT)]
    return rank_candidate_rooms(rooms, ctx)
