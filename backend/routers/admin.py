"""Platform admin API: schools, school admins, dashboard."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Job, ScheduleSettings, School, SchoolClass, Teacher, User
from app.models.job import JOB_PENDING, JOB_RUNNING
from app.models.user import ROLE_SCHOOL_ADMIN
from backend.bootstrap import slugify
from backend.deps import get_db, require_platform_admin
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


def _admin_counts(db: Session, school_ids: list[int]) -> dict[int, int]:
    result = {sid: 0 for sid in school_ids}
    if not school_ids:
        return result
    rows = db.execute(
        select(User.school_id, func.count())
        .where(
            User.school_id.in_(school_ids),
            User.role == ROLE_SCHOOL_ADMIN,
        )
        .group_by(User.school_id)
    ).all()
    for school_id, count in rows:
        result[int(school_id)] = int(count)
    return result


def _to_school_out(school: School, admins: int) -> SchoolOut:
    return SchoolOut(
        id=school.id,
        name=school.name,
        slug=school.slug,
        is_active=school.is_active,
        admins_count=admins,
    )


@router.get("/dashboard", response_model=PlatformDashboard)
def platform_dashboard(
    _: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformDashboard:
    schools_total = db.scalar(select(func.count()).select_from(School)) or 0
    schools_active = (
        db.scalar(
            select(func.count()).select_from(School).where(School.is_active.is_(True))
        )
        or 0
    )
    school_admins_total = (
        db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == ROLE_SCHOOL_ADMIN)
        )
        or 0
    )
    school_admins_active = (
        db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == ROLE_SCHOOL_ADMIN, User.is_active.is_(True))
        )
        or 0
    )
    jobs_active = (
        db.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.status.in_((JOB_PENDING, JOB_RUNNING)))
        )
        or 0
    )
    teachers_total = db.scalar(select(func.count()).select_from(Teacher)) or 0
    classes_total = db.scalar(select(func.count()).select_from(SchoolClass)) or 0

    schools_with_admin = {
        int(sid)
        for (sid,) in db.execute(
            select(User.school_id)
            .where(
                User.role == ROLE_SCHOOL_ADMIN,
                User.school_id.is_not(None),
            )
            .distinct()
        ).all()
        if sid is not None
    }
    all_school_ids = [int(sid) for (sid,) in db.execute(select(School.id)).all()]
    schools_without_admin = sum(
        1 for sid in all_school_ids if sid not in schools_with_admin
    )

    return PlatformDashboard(
        schools_total=int(schools_total),
        schools_active=int(schools_active),
        schools_inactive=int(schools_total) - int(schools_active),
        schools_without_admin=schools_without_admin,
        school_admins_total=int(school_admins_total),
        school_admins_active=int(school_admins_active),
        jobs_active=int(jobs_active),
        teachers_total=int(teachers_total),
        classes_total=int(classes_total),
    )


@router.get("/schools", response_model=list[SchoolOut])
def list_schools(
    _: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> list[SchoolOut]:
    schools = list(db.scalars(select(School).order_by(School.name)).all())
    counts = _admin_counts(db, [s.id for s in schools])
    return [_to_school_out(s, counts.get(s.id, 0)) for s in schools]


@router.post("/schools", response_model=SchoolOut, status_code=201)
def create_school(
    body: SchoolCreate,
    _: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> SchoolOut:
    slug = (body.slug or slugify(body.name)).lower()
    if db.scalars(select(School).where(School.slug == slug)).first():
        raise HTTPException(status_code=400, detail="Slug уже занят")
    school = School(name=body.name.strip(), slug=slug, is_active=True)
    db.add(school)
    db.flush()
    for level in ("elementary", "secondary"):
        db.add(
            ScheduleSettings(
                school_id=school.id,
                school_level=level,
                max_lessons_per_subject_per_day=2,
                classroom_mode="class_room",
                elementary_group_subjects_leave=True,
            )
        )
    db.commit()
    db.refresh(school)
    return _to_school_out(school, 0)


@router.patch("/schools/{school_id}", response_model=SchoolOut)
def update_school(
    school_id: int,
    body: SchoolUpdate,
    _: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> SchoolOut:
    school = db.get(School, school_id)
    if school is None:
        raise HTTPException(status_code=404, detail="Школа не найдена")
    data = body.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        school.name = data["name"].strip()
    if "is_active" in data and data["is_active"] is not None:
        school.is_active = data["is_active"]
    db.commit()
    db.refresh(school)
    counts = _admin_counts(db, [school.id])
    return _to_school_out(school, counts.get(school.id, 0))


@router.get("/schools/{school_id}/admins", response_model=list[SchoolAdminOut])
def list_school_admins(
    school_id: int,
    _: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> list[User]:
    school = db.get(School, school_id)
    if school is None:
        raise HTTPException(status_code=404, detail="Школа не найдена")
    return list(
        db.scalars(
            select(User)
            .where(
                User.school_id == school_id,
                User.role == ROLE_SCHOOL_ADMIN,
            )
            .order_by(User.email)
        ).all()
    )


@router.post("/schools/{school_id}/admins", response_model=AdminOut, status_code=201)
def create_school_admin(
    school_id: int,
    body: AdminCreate,
    _: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> AdminOut:
    school = db.get(School, school_id)
    if school is None:
        raise HTTPException(status_code=404, detail="Школа не найдена")
    email = body.email.lower().strip()
    existing = db.scalars(select(User).where(User.email == email)).first()
    if existing is not None:
        raise HTTPException(status_code=400, detail="Email уже зарегистрирован")

    user = User(
        email=email,
        password_hash=hash_password(body.password),
        role=ROLE_SCHOOL_ADMIN,
        school_id=school.id,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return AdminOut(
        id=user.id,
        email=email,
        password=body.password,
        message="Администратор школы создан",
    )


@router.patch("/users/{user_id}", response_model=SchoolAdminOut)
def update_school_admin(
    user_id: int,
    body: SchoolAdminUpdate,
    _: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> SchoolAdminOut:
    user = db.get(User, user_id)
    if user is None or user.role != ROLE_SCHOOL_ADMIN:
        raise HTTPException(status_code=404, detail="Админ школы не найден")

    data = body.model_dump(exclude_unset=True)
    if "email" in data and data["email"] is not None:
        new_email = str(data["email"]).lower().strip()
        clash = db.scalars(
            select(User).where(User.email == new_email, User.id != user.id)
        ).first()
        if clash is not None:
            raise HTTPException(status_code=400, detail="Email уже занят")
        user.email = new_email
    if "password" in data and data["password"]:
        user.password_hash = hash_password(data["password"])
    if "is_active" in data and data["is_active"] is not None:
        user.is_active = data["is_active"]

    if not data:
        raise HTTPException(status_code=400, detail="Нечего обновлять")

    db.commit()
    db.refresh(user)
    return SchoolAdminOut(
        id=user.id,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        password=data.get("password"),
    )
