"""Schedule grid API schemas."""
from pydantic import BaseModel, ConfigDict, Field

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
    subject_id: int | None = None
    is_exclusive: bool = False


class AssignmentsForClassOut(BaseModel):
    assignments: list[AssignmentChoiceOut]
    classrooms: list[ClassroomChoiceOut]


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
    time_limit_sec: float = 60.0
    random_seed: int = 1
    diagnose: bool = False


class AutoByTeacherStreamBody(BaseModel):
    teacher_id: int
    school_level: str = Field("elementary", pattern="^(elementary|secondary)$")
    diagnose: bool = False


class ClearScheduleBody(BaseModel):
    school_level: str | None = Field(None, pattern="^(elementary|secondary)$")
    class_id: int | None = None
    teacher_id: int | None = None


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
