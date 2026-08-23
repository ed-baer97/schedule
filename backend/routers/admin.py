"""Platform admin API: schools, school admins, dashboard."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.models import User
from app.services.admin_service import AdminService
from app.services.errors import ServiceError
from backend.deps import get_db, require_platform_admin
from backend.http_errors import raise_http
from backend.security import hash_password

router = APIRouter()


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


@router.get("/dashboard", response_model=PlatformDashboard)
def platform_dashboard(
    _: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformDashboard:
    data = AdminService(db).platform_dashboard()
    return PlatformDashboard(
        schools_total=data.schools_total,
        schools_active=data.schools_active,
        schools_inactive=data.schools_inactive,
        schools_without_admin=data.schools_without_admin,
        school_admins_total=data.school_admins_total,
        school_admins_active=data.school_admins_active,
        jobs_active=data.jobs_active,
        teachers_total=data.teachers_total,
        classes_total=data.classes_total,
    )


@router.get("/schools", response_model=list[SchoolOut])
def list_schools(
    _: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> list[SchoolOut]:
    return [
        SchoolOut(
            id=s.id,
            name=s.name,
            slug=s.slug,
            is_active=s.is_active,
            admins_count=s.admins_count,
        )
        for s in AdminService(db).list_schools()
    ]


@router.post("/schools", response_model=SchoolOut, status_code=201)
def create_school(
    body: SchoolCreate,
    _: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> SchoolOut:
    try:
        s = AdminService(db).create_school(name=body.name, slug=body.slug)
    except ServiceError as exc:
        raise_http(exc)
    return SchoolOut(
        id=s.id,
        name=s.name,
        slug=s.slug,
        is_active=s.is_active,
        admins_count=s.admins_count,
    )


@router.patch("/schools/{school_id}", response_model=SchoolOut)
def update_school(
    school_id: int,
    body: SchoolUpdate,
    _: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> SchoolOut:
    data = body.model_dump(exclude_unset=True)
    try:
        s = AdminService(db).update_school(
            school_id,
            name=data.get("name"),
            is_active=data.get("is_active"),
            fields_set=frozenset(data.keys()),
        )
    except ServiceError as exc:
        raise_http(exc)
    return SchoolOut(
        id=s.id,
        name=s.name,
        slug=s.slug,
        is_active=s.is_active,
        admins_count=s.admins_count,
    )


@router.get("/schools/{school_id}/admins", response_model=list[SchoolAdminOut])
def list_school_admins(
    school_id: int,
    _: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> list[User]:
    try:
        return AdminService(db).list_school_admins(school_id)
    except ServiceError as exc:
        raise_http(exc)


@router.post("/schools/{school_id}/admins", response_model=AdminOut, status_code=201)
def create_school_admin(
    school_id: int,
    body: AdminCreate,
    _: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> AdminOut:
    try:
        result = AdminService(db).create_school_admin(
            school_id,
            email=str(body.email),
            password_hash=hash_password(body.password),
            plain_password=body.password,
        )
    except ServiceError as exc:
        raise_http(exc)
    return AdminOut(
        id=result.id,
        email=result.email,
        password=result.password,
        message=result.message,
    )


@router.patch("/users/{user_id}", response_model=SchoolAdminOut)
def update_school_admin(
    user_id: int,
    body: SchoolAdminUpdate,
    _: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> SchoolAdminOut:
    data = body.model_dump(exclude_unset=True)
    password_hash = None
    plain_password = None
    if "password" in data and data["password"]:
        plain_password = data["password"]
        password_hash = hash_password(plain_password)
    try:
        result = AdminService(db).update_school_admin(
            user_id,
            email=str(data["email"]) if "email" in data else None,
            password_hash=password_hash,
            plain_password=plain_password,
            is_active=data.get("is_active"),
            fields_set=frozenset(data.keys()),
        )
    except ServiceError as exc:
        raise_http(exc)
    return SchoolAdminOut(
        id=result.id,
        email=result.email,
        role=result.role,
        is_active=result.is_active,
        created_at=result.created_at,
        password=result.password,
    )
