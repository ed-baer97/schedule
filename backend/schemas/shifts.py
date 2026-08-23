"""Shift API schemas.

Times are pre-formatted as HH:MM strings by ShiftService.serialize_shift.
"""
from pydantic import BaseModel, ConfigDict, Field


class ShiftLessonTimeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    day_of_week: int
    lesson_number: int
    time_start: str
    time_end: str


class ShiftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    school_level: str
    school_level_display: str
    start_lesson: int
    lessons_count: int
    working_days: int
    max_lessons_per_day: int
    class_hour_day: int | None = None
    class_hour_start: str | None = None
    class_hour_end: str | None = None
    lesson_times: list[ShiftLessonTimeOut] = []


class ShiftCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    school_level: str = Field(..., pattern="^(elementary|secondary)$")
    start_lesson: int = 1
    lessons_count: int = 6
    working_days: int = Field(5, ge=5, le=6)
    max_lessons_per_day: int = Field(7, ge=1, le=10)
    class_hour_day: int | None = Field(None, ge=1, le=6)
    class_hour_start: str | None = None
    class_hour_end: str | None = None


class ShiftUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=50)
    school_level: str | None = Field(None, pattern="^(elementary|secondary)$")
    start_lesson: int | None = None
    lessons_count: int | None = None
    working_days: int | None = Field(None, ge=5, le=6)
    max_lessons_per_day: int | None = Field(None, ge=1, le=10)
    class_hour_day: int | None = Field(None, ge=1, le=6)
    class_hour_start: str | None = None
    class_hour_end: str | None = None


class BellTimePair(BaseModel):
    """Empty strings mean «no bell for this lesson» (skip)."""

    time_start: str = ""
    time_end: str = ""


class BellScheduleUpdate(BaseModel):
    """Bell schedule editor payload.

    `common` covers lessons that apply to every working day except the
    class-hour day. `class_day` covers the day with the class hour
    (if any). Both are keyed by lesson number (as string, JSON-friendly).
    """

    common: dict[str, BellTimePair] = {}
    class_day: dict[str, BellTimePair] = {}


class BellScheduleApplied(BaseModel):
    inserted: int
    warnings: list[str] = []
