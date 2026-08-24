"""Platform admin API: schools, school admins, dashboard."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.models import User
from app.services.admin_service import AdminService
from backend.deps import get_db, require_platform_admin
from backend.schemas.admin import (
    AdminCreate,
    AdminOut,
    PlatformDashboard,
    SchoolAdminOut,
    SchoolAdminUpdate,
    SchoolCreate,
    SchoolOut,
    SchoolUpdate,
)

router = APIRouter()


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
    s = AdminService(db).create_school(name=body.name, slug=body.slug)
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
    s = AdminService(db).update_school(
        school_id,
        name=data.get("name"),
        is_active=data.get("is_active"),
        fields_set=frozenset(data.keys()),
    )
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
    return AdminService(db).list_school_admins(school_id)


@router.post("/schools/{school_id}/admins", response_model=AdminOut, status_code=201)
def create_school_admin(
    school_id: int,
    body: AdminCreate,
    _: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> AdminOut:
    result = AdminService(db).create_school_admin(
        school_id,
        email=str(body.email),
        password=body.password,
    )
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
    result = AdminService(db).update_school_admin(
        user_id,
        email=str(data["email"]) if "email" in data else None,
        password=data.get("password"),
        is_active=data.get("is_active"),
        fields_set=frozenset(data.keys()),
    )
    return SchoolAdminOut(
        id=result.id,
        email=result.email,
        role=result.role,
        is_active=result.is_active,
        created_at=result.created_at,
        password=result.password,
    )
