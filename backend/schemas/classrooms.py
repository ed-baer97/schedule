"""Classroom API schemas."""
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from backend.schemas.common import SubjectBrief, TeacherBrief


def _empty_level(value: object) -> object:
    if value == "":
        return None
    return value


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
    school_level: str | None = None
    subgroup_only: bool = False
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
    school_level: str | None = None
    subgroup_only: bool = False
    teacher_ids: list[int] = []

    @field_validator("school_level", mode="before")
    @classmethod
    def blank_level(cls, value: object) -> object:
        return _empty_level(value)

    @model_validator(mode="after")
    def exclusive_requires_subject(self) -> "ClassroomCreate":
        if self.is_exclusive and not self.subject_ids:
            raise ValueError("Фиксированный кабинет должен иметь предмет")
        if self.school_level is not None and self.school_level not in (
            "elementary",
            "secondary",
        ):
            raise ValueError("Уровень кабинета: начальная, основная или общий")
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
    school_level: str | None = None
    subgroup_only: bool | None = None
    teacher_ids: list[int] | None = None

    @field_validator("school_level", mode="before")
    @classmethod
    def blank_level(cls, value: object) -> object:
        return _empty_level(value)

    @model_validator(mode="after")
    def known_level(self) -> "ClassroomUpdate":
        if self.school_level is not None and self.school_level not in (
            "elementary",
            "secondary",
        ):
            raise ValueError("Уровень кабинета: начальная, основная или общий")
        return self
