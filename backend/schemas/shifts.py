"""Shift API schemas."""
from datetime import time

from pydantic import BaseModel, ConfigDict, Field, field_serializer


def _fmt_time(v: time | str | None) -> str | None:
    if v is None:
        return None
    if isinstance(v, time):
        return v.strftime("%H:%M")
    return str(v) if v else None


class ShiftLessonTimeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    day_of_week: int
    lesson_number: int
    time_start: time | str
    time_end: time | str

    @field_serializer("time_start")
    def ser_ts(self, v: time | str) -> str:
        return _fmt_time(v) or ""

    @field_serializer("time_end")
    def ser_te(self, v: time | str) -> str:
        return _fmt_time(v) or ""


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
    class_hour_start: time | str | None = None
    class_hour_end: time | str | None = None
    lesson_times: list[ShiftLessonTimeOut] = []

    @field_serializer("class_hour_start")
    def ser_chs(self, v: time | str | None) -> str | None:
        return _fmt_time(v)

    @field_serializer("class_hour_end")
    def ser_che(self, v: time | str | None) -> str | None:
        return _fmt_time(v)


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
