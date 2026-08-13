"""Teacher API schemas."""
from pydantic import BaseModel, ConfigDict


class ClassroomBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str
    name: str | None = None
    display_name: str


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
