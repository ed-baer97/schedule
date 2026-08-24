"""Schedule service dataclasses and helpers."""
from __future__ import annotations

from dataclasses import dataclass

from app.domain import time_range_label
from app.models import Shift
from app.services.dto import (
    ClassroomChoiceData,
    ClassroomWarningData,
    ScheduleSettingsData,
    SchoolClassRowData,
    TeacherBriefData,
)


@dataclass
class ShiftBriefData:
    id: int
    name: str
    school_level: str
    working_days: int
    max_lessons_per_day: int
    start_lesson: int
    lessons_count: int
    class_hour_day: int | None = None
    class_hour_time_label: str | None = None


@dataclass
class AssignmentChoiceData:
    id: int
    subject_id: int
    subject_name: str
    subject_color: str
    teacher_id: int | None
    teacher_name: str | None
    group_number: int | None
    remaining_hours: int
    preferred_classroom_id: int | None


@dataclass
class Placement:
    """One schedule cell to insert (sole write-path for ScheduleCell rows)."""

    assignment_id: int
    class_id: int
    day_of_week: int
    lesson_number: int
    classroom_id: int | None = None


@dataclass
class GridData:
    school_level: str
    current_shift_id: int | None
    current_shift: ShiftBriefData | None
    shifts: list[ShiftBriefData]
    classes: list[SchoolClassRowData]
    day_names: list[str]
    working_days: int
    max_lessons: int
    lessons_range: list[int]
    lesson_times_by_day: dict[int, dict[int, str]]
    class_hour_time_label: str
    cells: list[dict]
    classroom_warnings: list[ClassroomWarningData]
    settings: ScheduleSettingsData | None


@dataclass
class AssignmentsForClassData:
    assignments: list[AssignmentChoiceData]
    classrooms: list[ClassroomChoiceData]


@dataclass
class AutoPageDataRaw:
    teachers: list[TeacherBriefData]
    classes: list[SchoolClassRowData]
    elementary_warnings: list[ClassroomWarningData]
    secondary_warnings: list[ClassroomWarningData]
    elementary_settings: ScheduleSettingsData | None
    secondary_settings: ScheduleSettingsData | None
    shifts_elementary: list[ShiftBriefData]
    shifts_secondary: list[ShiftBriefData]


@dataclass
class SettingsPairData:
    elementary: ScheduleSettingsData | None
    secondary: ScheduleSettingsData | None


def _shift_brief(s: Shift) -> ShiftBriefData:
    return ShiftBriefData(
        id=s.id,
        name=s.name,
        school_level=s.school_level,
        working_days=s.working_days,
        max_lessons_per_day=s.max_lessons_per_day,
        start_lesson=s.start_lesson,
        lessons_count=s.lessons_count,
        class_hour_day=s.class_hour_day,
        class_hour_time_label=time_range_label(s.class_hour_start, s.class_hour_end),
    )


def _warnings(raw) -> list[ClassroomWarningData]:
    return [ClassroomWarningData(type=t, message=msg) for (t, msg, _e) in raw]
