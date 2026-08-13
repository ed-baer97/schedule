"""Classroom API schemas."""
from pydantic import BaseModel, ConfigDict


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


class ClassroomCreate(BaseModel):
    number: str
    name: str | None = None
    capacity: int | None = None
    classes_capacity: int = 1
    floor: int | None = None
    building: str | None = None


class ClassroomUpdate(BaseModel):
    number: str | None = None
    name: str | None = None
    capacity: int | None = None
    classes_capacity: int | None = None
    floor: int | None = None
    building: str | None = None
