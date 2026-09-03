"""Schedule grid API schemas."""
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.schemas.common import TeacherBrief


class ShiftBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    school_level: str
    working_days: int
    max_lessons_per_day: int
    start_lesson: int
    lessons_count: int
    class_hour_day: int | None = None
    class_hour_time_label: str | None = None
    class_hour_lessons_count: int | None = None


class SchoolClassRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    grade: int
    school_level: str
    shift_id: int | None = None
    home_classroom_id: int | None = None


class ScheduleCellOut(BaseModel):
    id: int
    class_id: int
    day_of_week: int
    lesson_number: int
    assignment_id: int
    classroom_id: int | None = None
    subject_id: int
    subject_name: str
    subject_color: str
    teacher_id: int | None = None
    teacher_name: str | None = None
    group_number: int | None = None
    classroom_name: str | None = None
    requires_fixed_classroom: bool = False


class ScheduleSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    school_level: str
    max_lessons_per_subject_per_day: int
    classroom_mode: str
    elementary_group_subjects_leave: bool
    pref_teacher_gaps: int = 5
    pref_hard_subjects_early: int = 5
    pref_adjacent_pairs: int = 5
    pref_classroom_stability: int = 5


class ClassroomWarningOut(BaseModel):
    type: str
    message: str


class ScheduleGridOut(BaseModel):
    school_level: str
    current_shift_id: int | None = None
    current_shift: ShiftBrief | None = None
    shifts: list[ShiftBrief]
    classes: list[SchoolClassRow]
    day_names: list[str]
    working_days: int
    max_lessons: int
    lessons_range: list[int]
    lesson_times_by_day: dict[int, dict[int, str]]
    class_hour_time_label: str
    cells: list[ScheduleCellOut]
    classroom_warnings: list[ClassroomWarningOut]
    settings: ScheduleSettingsOut | None = None


class AssignmentChoiceOut(BaseModel):
    id: int
    subject_id: int
    subject_name: str
    subject_color: str
    teacher_id: int | None = None
    teacher_name: str | None = None
    group_number: int | None = None
    remaining_hours: int
    preferred_classroom_id: int | None = None
    requires_fixed_classroom: bool = False


class ClassroomChoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str
    name: str | None = None
    display_name: str
    subject_ids: list[int] = []
    is_exclusive: bool = False
    school_level: str | None = None
    subgroup_only: bool = False
    classes_capacity: int = 1


class AssignmentsForClassOut(BaseModel):
    assignments: list[AssignmentChoiceOut]
    classrooms: list[ClassroomChoiceOut]


class TeacherDayOccupantOut(BaseModel):
    class_id: int
    class_name: str
    subject_name: str
    subject_color: str
    classroom_name: str | None = None
    group_number: int | None = None


class TeacherDayLessonOut(BaseModel):
    lesson: int
    time_label: str | None = None
    is_candidate: bool = False
    is_gap: bool = False
    overlaps_current: bool = False
    occupants: list[TeacherDayOccupantOut] = []


class TeacherDayShiftOut(BaseModel):
    shift_id: int | None = None
    shift_name: str
    is_current: bool = False
    lessons: list[TeacherDayLessonOut]


class TeacherDayOut(BaseModel):
    teacher_id: int
    teacher_name: str
    day_of_week: int
    day_name: str
    other_shift_gap: str | None = None
    shifts: list[TeacherDayShiftOut]


class ScheduleCellCreate(BaseModel):
    class_id: int
    day_of_week: int = Field(..., ge=1, le=6)
    lesson_number: int = Field(..., ge=0, le=20)
    assignment_id: int
    classroom_id: int | None = None


class ScheduleCellMove(BaseModel):
    day_of_week: int = Field(..., ge=1, le=6)
    lesson_number: int = Field(..., ge=0, le=20)
    class_id: int | None = None
    classroom_id: int | None = None
    set_classroom: bool = False


class ScheduleCellSwapClassroom(BaseModel):
    other_cell_id: int


class ScheduleCellSwapOut(BaseModel):
    cell: ScheduleCellOut
    other: ScheduleCellOut


class AutoPageData(BaseModel):
    teachers: list[TeacherBrief]
    classes: list[SchoolClassRow]
    elementary_warnings: list[ClassroomWarningOut]
    secondary_warnings: list[ClassroomWarningOut]
    elementary_settings: ScheduleSettingsOut | None = None
    secondary_settings: ScheduleSettingsOut | None = None
    shifts_elementary: list[ShiftBrief]
    shifts_secondary: list[ShiftBrief]


class AutoAllStreamBody(BaseModel):
    school_level: str = Field("elementary", pattern="^(elementary|secondary)$")
    shift_id: int
    time_limit_sec: float = Field(60.0, ge=1, le=86_400)
    random_seed: int = 1
    diagnose: bool = False
    split: str = Field("shift", pattern="^(shift|grade_bands)$")
    hours_first: str = Field("more", pattern="^(more|fewer)$")


class AutoByTeacherStreamBody(BaseModel):
    teacher_id: int
    school_level: str = Field("elementary", pattern="^(elementary|secondary)$")
    diagnose: bool = False


class ClearScheduleBody(BaseModel):
    school_level: str | None = Field(None, pattern="^(elementary|secondary)$")
    class_id: int | None = None
    teacher_id: int | None = None
    days_of_week: list[int] | None = Field(None, min_length=1)

    @field_validator("days_of_week")
    @classmethod
    def _days_of_week(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return None
        seen: set[int] = set()
        days: list[int] = []
        for day in value:
            if day < 1 or day > 6:
                raise ValueError("days_of_week must be 1..6 (Mon..Sat)")
            if day not in seen:
                seen.add(day)
                days.append(day)
        return days


class ClearScheduleResult(BaseModel):
    count: int


class SettingsPair(BaseModel):
    elementary: ScheduleSettingsOut | None = None
    secondary: ScheduleSettingsOut | None = None


class SettingsUpdate(BaseModel):
    max_lessons_per_subject_per_day: int = Field(..., ge=1, le=5)
    classroom_mode: str = Field(..., pattern="^(class_room|teacher_room)$")
    elementary_group_subjects_leave: bool | None = None
    pref_teacher_gaps: int = Field(5, ge=0, le=10)
    pref_hard_subjects_early: int = Field(5, ge=0, le=10)
    pref_adjacent_pairs: int = Field(5, ge=0, le=10)
    pref_classroom_stability: int = Field(5, ge=0, le=10)


class ExplainSlotBody(BaseModel):
    assignment_id: int
    day_of_week: int = Field(..., ge=1, le=6)
    lesson_number: int = Field(..., ge=0, le=20)
    classroom_id: int | None = None
    cell_id: int | None = None


class ExplainSlotOut(BaseModel):
    allowed: bool
    blockers: list[str]
    alternatives: list[dict]
    text: str
    llm_used: bool


class RepairBody(BaseModel):
    school_level: str = Field("elementary", pattern="^(elementary|secondary)$")
    teacher_id: int | None = None
    class_id: int | None = None


class AssistBody(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)
    school_level: str = Field("elementary", pattern="^(elementary|secondary)$")
    shift_id: int | None = None
    apply: bool = False


class AssistMoveOut(BaseModel):
    cell_id: int
    subject: str
    class_name: str
    from_day: int
    from_lesson: int
    to_day: int
    to_lesson: int
    allowed: bool
    applied: bool
    blockers: list[str]
    label: str


class AssistOut(BaseModel):
    interpretation: str
    llm_used: bool
    preference_updates: dict[str, int]
    preferences_applied: bool
    moves: list[AssistMoveOut]
    applied_moves: int
    rejected: list[AssistMoveOut]
