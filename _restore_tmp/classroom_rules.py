"""Classroom suitability and placement cost (no Session)."""
from __future__ import annotations

from dataclasses import dataclass

# Soft costs for auto-scheduler / CP-SAT (lower = better).
COST_OWNER_SUBJECT = 0
COST_SAME_SUBJECT = 10
COST_OTHER_SUBJECT = 50
COST_GENERAL = 40
COST_PREFERRED_BONUS = -5


@dataclass(frozen=True)
class ClassroomFact:
    id: int
    subject_id: int | None
    is_exclusive: bool
    classes_capacity: int = 1


@dataclass(frozen=True)
class PlacementContext:
    """Facts needed to score a room for an assignment."""

    subject_id: int
    requires_fixed_classroom: bool
    teacher_home_classroom_id: int | None = None
    preferred_classroom_id: int | None = None
    class_home_classroom_id: int | None = None
    classroom_mode: str = "class_room"  # class_room | teacher_room


def room_allows_subject(
    room: ClassroomFact,
    *,
    subject_id: int,
    requires_fixed_classroom: bool,
) -> bool:
    """
    Hard rule: can this subject be placed in this classroom?

    - Fixed subject → only rooms tagged with that subject.
    - Exclusive room → only its subject.
    - Subject-tagged non-exclusive → any non-fixed subject.
    - Untagged (general) room → any non-fixed subject.
    """
    if requires_fixed_classroom:
        return room.subject_id == subject_id

    if room.is_exclusive:
        return room.subject_id == subject_id

    # Non-fixed subject: general rooms and non-exclusive subject rooms OK.
    return True


def room_denial_message(
    room: ClassroomFact,
    *,
    subject_id: int,
    subject_name: str,
    requires_fixed_classroom: bool,
    room_display_name: str,
    room_subject_name: str | None = None,
) -> str | None:
    """Human-readable reason if room_allows_subject is False."""
    if room_allows_subject(
        room,
        subject_id=subject_id,
        requires_fixed_classroom=requires_fixed_classroom,
    ):
        return None
    if requires_fixed_classroom:
        return (
            f"Предмет «{subject_name}» требует фиксированный кабинет — "
            f"нельзя ставить в {room_display_name}"
        )
    if room.is_exclusive:
        subj = room_subject_name or "своего предмета"
        return f"Кабинет {room_display_name} только для {subj}"
    return f"Кабинет {room_display_name} недоступен для «{subject_name}»"


def placement_cost(
    room: ClassroomFact,
    ctx: PlacementContext,
) -> int | None:
    """
    Soft cost for placing ctx into room. None = forbidden.

    Priority (lower cost better):
    1. Teacher home + room's subject matches assignment subject → 0
    2. Same subject as room (other teacher) → low
    3. General / other non-exclusive subject room → medium
    """
    if not room_allows_subject(
        room,
        subject_id=ctx.subject_id,
        requires_fixed_classroom=ctx.requires_fixed_classroom,
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
    if room.subject_id == ctx.subject_id:
        if ctx.teacher_home_classroom_id == room.id:
            cost = COST_OWNER_SUBJECT
        else:
            cost = COST_SAME_SUBJECT
    elif room.subject_id is None:
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
