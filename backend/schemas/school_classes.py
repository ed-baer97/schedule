"""School class API schemas."""
from pydantic import BaseModel, ConfigDict, Field


class ShiftBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    school_level: str


class ClassroomBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str
    name: str | None = None
    display_name: str


class SchoolClassOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    grade: int
    school_level: str
    school_level_display: str
    shift_id: int | None = None
    students_count: int | None = None
    home_classroom_id: int | None = None
    shift: ShiftBrief | None = None
    home_classroom: ClassroomBrief | None = None


class SchoolClassCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=10)
    school_level: str = Field(..., pattern="^(elementary|secondary)$")
    shift_id: int | None = None
    home_classroom_id: int | None = None
    students_count: int | None = None


class SchoolClassUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=10)
    school_level: str | None = Field(None, pattern="^(elementary|secondary)$")
    shift_id: int | None = None
    home_classroom_id: int | None = None
    students_count: int | None = None


class BatchShiftBody(BaseModel):
    class_ids: list[int]
    shift_id: int | None = None
