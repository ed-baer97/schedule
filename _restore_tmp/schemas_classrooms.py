"""Classroom API schemas."""
from pydantic import BaseModel, ConfigDict, model_validator

from backend.schemas.common import SubjectBrief


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
    subject_id: int | None = None
    is_exclusive: bool = False
    subject: SubjectBrief | None = None


class ClassroomCreate(BaseModel):
    number: str
    name: str | None = None
    capacity: int | None = None
    classes_capacity: int = 1
    floor: int | None = None
    building: str | None = None
    subject_id: int | None = None
    is_exclusive: bool = False

    @model_validator(mode="after")
    def exclusive_requires_subject(self) -> "ClassroomCreate":
        if self.is_exclusive and self.subject_id is None:
            raise ValueError("Фиксированный кабинет должен иметь предмет")
        return self


class ClassroomUpdate(BaseModel):
    number: str | None = None
    name: str | None = None
    capacity: int | None = None
    classes_capacity: int | None = None
    floor: int | None = None
    building: str | None = None
    subject_id: int | None = None
    is_exclusive: bool | None = None
