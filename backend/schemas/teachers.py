"""Teacher API schemas."""
from pydantic import BaseModel, ConfigDict

from backend.schemas.common import ClassroomBrief


class TeacherOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: str | None = None
    phone: str | None = None
    home_classroom_id: int | None = None
    home_classroom: ClassroomBrief | None = None


class TeacherCreate(BaseModel):
    full_name: str
    email: str | None = None
    phone: str | None = None
    home_classroom_id: int | None = None


class TeacherUpdate(BaseModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    home_classroom_id: int | None = None


class TeacherSubjectHoursOut(BaseModel):
    subject_id: int
    subject_name: str
    color: str
    hours: int


class TeacherShiftBriefOut(BaseModel):
    id: int
    name: str
    school_level: str
    hours: int


class TeacherLoadOut(BaseModel):
    id: int
    full_name: str
    subjects: list[TeacherSubjectHoursOut]
    shifts: list[TeacherShiftBriefOut]
    total_hours: int
    unassigned_shift_hours: int = 0
    has_classes_without_shift: bool = False
