"""Pure domain helpers (no Session, no FastAPI)."""
from app.domain.assignment import hours_exhausted, remaining_hours
from app.domain.classroom_rules import (
    ClassroomFact,
    PlacementContext,
    candidate_rooms_for,
    placement_cost,
    rank_candidate_rooms,
    room_allows_subject,
    room_denial_message,
    room_has_subject,
)
from app.domain.days import DAY_NAMES, SHORT_DAY_NAMES, fmt_time, time_range_label
from app.domain.names import normalize_person_name
from app.domain.schedule_facts import BusySlotFact, SlotFact, UnitFact
from app.domain.schedule_rules import (
    classroom_at_capacity,
    groups_can_share_slot,
    occupancy_blocks_unit,
    overlapping_classroom_busy,
    slot_facts_conflict,
    slots_conflict,
    subject_day_limit_reached,
    teacher_busy_at_slot,
    teacher_class_day_limit_reached,
    time_intervals_overlap,
    units_cannot_share_class_slot,
)
from app.domain.school_class import grade_from_name, level_from_grade
from app.domain.school_level import level_label

__all__ = [
    "DAY_NAMES",
    "SHORT_DAY_NAMES",
    "fmt_time",
    "time_range_label",
    "grade_from_name",
    "level_from_grade",
    "level_label",
    "normalize_person_name",
    "remaining_hours",
    "hours_exhausted",
    "slots_conflict",
    "slot_facts_conflict",
    "time_intervals_overlap",
    "subject_day_limit_reached",
    "teacher_class_day_limit_reached",
    "groups_can_share_slot",
    "units_cannot_share_class_slot",
    "occupancy_blocks_unit",
    "teacher_busy_at_slot",
    "overlapping_classroom_busy",
    "classroom_at_capacity",
    "UnitFact",
    "SlotFact",
    "BusySlotFact",
    "ClassroomFact",
    "PlacementContext",
    "room_allows_subject",
    "room_denial_message",
    "room_has_subject",
    "placement_cost",
    "rank_candidate_rooms",
    "candidate_rooms_for",
]
