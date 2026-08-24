"""Platform admin API schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class SchoolCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str | None = Field(default=None, max_length=80)


class SchoolUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    is_active: bool | None = None


class SchoolOut(BaseModel):
    id: int
    name: str
    slug: str
    is_active: bool
    admins_count: int = 0

    model_config = {"from_attributes": True}


class PlatformDashboard(BaseModel):
    schools_total: int
    schools_active: int
    schools_inactive: int
    schools_without_admin: int
    school_admins_total: int
    school_admins_active: int
    jobs_active: int
    teachers_total: int
    classes_total: int


class AdminCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class AdminOut(BaseModel):
    id: int
    email: str
    password: str
    message: str


class SchoolAdminOut(BaseModel):
    id: int
    email: str
    role: str
    is_active: bool
    created_at: datetime | None = None
    password: str | None = None

    model_config = {"from_attributes": True}


class SchoolAdminUpdate(BaseModel):
    password: str | None = Field(default=None, min_length=8)
    is_active: bool | None = None
    email: EmailStr | None = None
