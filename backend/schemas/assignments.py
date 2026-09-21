"""Teaching assignment API schemas."""
from pydantic import BaseModel, Field, field_validator

from app.domain.schedule_variant import snap_hours

from backend.schemas.common import (
    ClassroomBrief,
    SchoolClassBrief,
    SubjectBrief,
    TeacherBrief,
)

__all__ = [
    "SubjectBrief",
    "TeacherBrief",
    "SchoolClassBrief",
    "ClassroomBrief",
    "AssignmentOut",
    "AssignmentCreate",
    "AssignmentUpdate",
    "AssignTeacherBody",
]


class AssignmentOut(BaseModel):
    id: int
    subject_id: int
    teacher_id: int | None = None
    class_id: int
    hours_per_week: float
    group_number: int | None = None
    preferred_classroom_id: int | None = None
    subject: SubjectBrief
    teacher: TeacherBrief | None = None
    school_class: SchoolClassBrief
    preferred_classroom: ClassroomBrief | None = None


class AssignmentCreate(BaseModel):
    subject_id: int
    teacher_id: int | None = None
    class_id: int
    hours_per_week: float = Field(..., ge=0.25, le=30)
    group_number: int | None = Field(None, ge=1, le=4)
    preferred_classroom_id: int | None = None

    @field_validator("hours_per_week")
    @classmethod
    def _snap_create_hours(cls, value: float) -> float:
        return snap_hours(value)


class AssignmentUpdate(BaseModel):
    subject_id: int | None = None
    teacher_id: int | None = None
    class_id: int | None = None
    hours_per_week: float | None = Field(None, ge=0.25, le=30)
    group_number: int | None = Field(None, ge=1, le=4)
    preferred_classroom_id: int | None = None
    clear_teacher: bool = False
    clear_group: bool = False
    clear_preferred_classroom: bool = False

    @field_validator("hours_per_week")
    @classmethod
    def _snap_update_hours(cls, value: float | None) -> float | None:
        return None if value is None else snap_hours(value)


class AssignTeacherBody(BaseModel):
    teacher_id: int | None = None
