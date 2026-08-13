"""Teaching assignment API schemas."""
from pydantic import BaseModel, ConfigDict, Field


class SubjectBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    color: str | None = None
    display_color: str


class TeacherBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str


class SchoolClassBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    school_level: str
    grade: int


class ClassroomBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str
    name: str | None = None
    display_name: str


class AssignmentOut(BaseModel):
    id: int
    subject_id: int
    teacher_id: int | None = None
    class_id: int
    hours_per_week: int
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
    hours_per_week: int = Field(..., ge=1, le=30)
    group_number: int | None = Field(None, ge=1, le=4)
    preferred_classroom_id: int | None = None


class AssignmentUpdate(BaseModel):
    subject_id: int | None = None
    teacher_id: int | None = None
    class_id: int | None = None
    hours_per_week: int | None = Field(None, ge=1, le=30)
    group_number: int | None = Field(None, ge=1, le=4)
    preferred_classroom_id: int | None = None
    clear_teacher: bool = False
    clear_group: bool = False
    clear_preferred_classroom: bool = False


class AssignTeacherBody(BaseModel):
    teacher_id: int | None = None
