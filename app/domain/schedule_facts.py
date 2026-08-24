"""Flat schedule facts for solvers and shared conflict predicates (no Session)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class UnitFact:
    """One teachable hour of a TeachingAssignment."""

    unit_id: str
    assignment_id: int
    teacher_id: int | None
    class_id: int
    subject_id: int | None
    group_number: int | None
    school_level: str


@dataclass(frozen=True)
class SlotFact:
    """One (class, day, lesson) grid cell; optional bell interval for time overlap."""

    slot_id: str
    class_id: int
    day: int
    lesson: int
    shift_id: int | None
    interval: tuple[Any, Any] | None = None


@dataclass(frozen=True)
class BusySlotFact:
    """Existing occupancy used for teacher/classroom/class conflict checks."""

    shift_id: int | None
    day: int
    lesson: int
    interval: tuple[Any, Any] | None = None
    assignment_id: int | None = None
    subject_id: int | None = None
    group_number: int | None = None
    class_id: int | None = None
    classroom_id: int | None = None
    source_cell_id: int | None = None
