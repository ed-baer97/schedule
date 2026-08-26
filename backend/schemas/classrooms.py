"""Classroom API schemas."""
from pydantic import BaseModel, ConfigDict, model_validator

from backend.schemas.common import SubjectBrief, TeacherBrief


class ClassroomOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str
    name: str | None = None
    capacity: int | None = None
    classes_capacity: int | None = 1
    floor: int | None = None
    building: str | None = None
    display_name: str
    subject_ids: list[int] = []
    is_exclusive: bool = False
    subjects: list[SubjectBrief] = []
    teachers: list[TeacherBrief] = []


class ClassroomCreate(BaseModel):
    number: str
    name: str | None = None
    capacity: int | None = None
    classes_capacity: int = 1
    floor: int | None = None
    building: str | None = None
    subject_ids: list[int] = []
    is_exclusive: bool = False
    teacher_ids: list[int] = []

    @model_validator(mode="after")
    def exclusive_requires_subject(self) -> "ClassroomCreate":
        if self.is_exclusive and not self.subject_ids:
            raise ValueError("Фиксированный кабинет должен иметь предмет")
        return self


class ClassroomUpdate(BaseModel):
    number: str | None = None
    name: str | None = None
    capacity: int | None = None
    classes_capacity: int | None = None
    floor: int | None = None
    building: str | None = None
    subject_ids: list[int] | None = None
    is_exclusive: bool | None = None
    teacher_ids: list[int] | None = None
