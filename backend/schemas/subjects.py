"""Subject API schemas."""
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import Subject
from backend.schemas.common import ClassroomBrief

_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


class SubjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    color: str | None = None
    display_color: str
    requires_fixed_classroom: bool
    classrooms: list[ClassroomBrief] = []


class SubjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    color: str = Subject.DEFAULT_COLOR
    requires_fixed_classroom: bool = False

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: str) -> str:
        if v and _HEX_COLOR.match(v):
            return v
        return Subject.DEFAULT_COLOR


class SubjectUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    color: str | None = None
    requires_fixed_classroom: bool | None = None

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if _HEX_COLOR.match(v):
            return v
        return Subject.DEFAULT_COLOR


class SubjectAssignClassRow(BaseModel):
    id: int
    name: str
    grade: int
    hours_per_week: int
    teacher_ids: list[int] = []
    is_split: bool = False


class SubjectAssignTeacherRow(BaseModel):
    id: int
    full_name: str


class SubjectAssignmentsView(BaseModel):
    subject: SubjectOut
    school_level: str
    classes: list[SubjectAssignClassRow]
    attached_teachers: list[SubjectAssignTeacherRow]
    all_teachers: list[SubjectAssignTeacherRow]


class SubjectAssignmentsSave(BaseModel):
    school_level: str = Field(..., pattern="^(elementary|secondary)$")
    teacher_ids: list[int] = []
    selections: dict[str, list[int]] = Field(
        default_factory=dict,
        description="class_id (as string) -> list of teacher_ids (0..2)",
    )


class SubjectAssignmentsSaveResult(BaseModel):
    ok: bool = True
    errors: list[str] = []


class SubjectColorUpdate(BaseModel):
    color: str

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: str) -> str:
        if _HEX_COLOR.match(v):
            return v
        return Subject.DEFAULT_COLOR


class SubjectColorOut(BaseModel):
    id: int
    display_color: str
