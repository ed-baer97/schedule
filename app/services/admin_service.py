"""Platform admin: schools, school admins, platform dashboard."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Job, ScheduleSettings, School, SchoolClass, Teacher, User
from app.models.job import JOB_PENDING, JOB_RUNNING, JOB_CANCELLING
from app.models.user import ROLE_SCHOOL_ADMIN
from app.passwords import hash_password
from app.services.errors import BadRequestError, NotFoundError


def slugify(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9а-яё]+", "-", s, flags=re.IGNORECASE)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "school"


@dataclass
class PlatformDashboardData:
    schools_total: int
    schools_active: int
    schools_inactive: int
    schools_without_admin: int
    school_admins_total: int
    school_admins_active: int
    jobs_active: int
    teachers_total: int
    classes_total: int


@dataclass
class SchoolData:
    id: int
    name: str
    slug: str
    is_active: bool
    admins_count: int = 0


@dataclass
class SchoolAdminData:
    id: int
    email: str
    role: str
    is_active: bool
    created_at: datetime | None = None
    password: str | None = None


@dataclass
class AdminCreateResultData:
    id: int
    email: str
    password: str
    message: str


class AdminService:
    def __init__(self, db: Session):
        self.db = db

    def platform_dashboard(self) -> PlatformDashboardData:
        schools_total = self.db.scalar(select(func.count()).select_from(School)) or 0
        schools_active = (
            self.db.scalar(
                select(func.count())
                .select_from(School)
                .where(School.is_active.is_(True))
            )
            or 0
        )
        school_admins_total = (
            self.db.scalar(
                select(func.count())
                .select_from(User)
                .where(User.role == ROLE_SCHOOL_ADMIN)
            )
            or 0
        )
        school_admins_active = (
            self.db.scalar(
                select(func.count())
                .select_from(User)
                .where(User.role == ROLE_SCHOOL_ADMIN, User.is_active.is_(True))
            )
            or 0
        )
        jobs_active = (
            self.db.scalar(
                select(func.count())
                .select_from(Job)
                .where(Job.status.in_((JOB_PENDING, JOB_RUNNING, JOB_CANCELLING)))
            )
            or 0
        )
        teachers_total = (
            self.db.scalar(select(func.count()).select_from(Teacher)) or 0
        )
        classes_total = (
            self.db.scalar(select(func.count()).select_from(SchoolClass)) or 0
        )

        schools_with_admin = {
            int(sid)
            for (sid,) in self.db.execute(
                select(User.school_id)
                .where(
                    User.role == ROLE_SCHOOL_ADMIN,
                    User.school_id.is_not(None),
                )
                .distinct()
            ).all()
            if sid is not None
        }
        all_school_ids = [
            int(sid) for (sid,) in self.db.execute(select(School.id)).all()
        ]
        schools_without_admin = sum(
            1 for sid in all_school_ids if sid not in schools_with_admin
        )

        return PlatformDashboardData(
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

    def _admin_counts(self, school_ids: list[int]) -> dict[int, int]:
        result = {sid: 0 for sid in school_ids}
        if not school_ids:
            return result
        rows = self.db.execute(
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

    def _school_data(self, school: School, admins: int) -> SchoolData:
        return SchoolData(
            id=school.id,
            name=school.name,
            slug=school.slug,
            is_active=school.is_active,
            admins_count=admins,
        )

    def list_schools(self) -> list[SchoolData]:
        schools = list(self.db.scalars(select(School).order_by(School.name)).all())
        counts = self._admin_counts([s.id for s in schools])
        return [self._school_data(s, counts.get(s.id, 0)) for s in schools]

    def create_school(
        self, *, name: str, slug: str | None = None
    ) -> SchoolData:
        resolved = (slug or slugify(name)).lower()
        if self.db.scalars(select(School).where(School.slug == resolved)).first():
            raise BadRequestError("Slug уже занят")
        school = School(name=name.strip(), slug=resolved, is_active=True)
        self.db.add(school)
        self.db.flush()
        for level in ("elementary", "secondary"):
            self.db.add(
                ScheduleSettings(
                    school_id=school.id,
                    school_level=level,
                    max_lessons_per_subject_per_day=2,
                    classroom_mode="class_room",
                    elementary_group_subjects_leave=True,
                )
            )
        self.db.commit()
        self.db.refresh(school)
        return self._school_data(school, 0)

    def update_school(
        self,
        school_id: int,
        *,
        name: str | None = None,
        is_active: bool | None = None,
        fields_set: frozenset[str] | None = None,
    ) -> SchoolData:
        school = self.db.get(School, school_id)
        if school is None:
            raise NotFoundError("Школа не найдена")
        fields_set = fields_set or frozenset()
        if "name" in fields_set and name is not None:
            school.name = name.strip()
        if "is_active" in fields_set and is_active is not None:
            school.is_active = is_active
        self.db.commit()
        self.db.refresh(school)
        counts = self._admin_counts([school.id])
        return self._school_data(school, counts.get(school.id, 0))

    def list_school_admins(self, school_id: int) -> list[User]:
        school = self.db.get(School, school_id)
        if school is None:
            raise NotFoundError("Школа не найдена")
        return list(
            self.db.scalars(
                select(User)
                .where(
                    User.school_id == school_id,
                    User.role == ROLE_SCHOOL_ADMIN,
                )
                .order_by(User.email)
            ).all()
        )

    def create_school_admin(
        self,
        school_id: int,
        *,
        email: str,
        password: str,
    ) -> AdminCreateResultData:
        school = self.db.get(School, school_id)
        if school is None:
            raise NotFoundError("Школа не найдена")
        normalized = email.lower().strip()
        existing = self.db.scalars(
            select(User).where(User.email == normalized)
        ).first()
        if existing is not None:
            raise BadRequestError("Email уже зарегистрирован")

        user = User(
            email=normalized,
            password_hash=hash_password(password),
            role=ROLE_SCHOOL_ADMIN,
            school_id=school.id,
            is_active=True,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return AdminCreateResultData(
            id=user.id,
            email=normalized,
            password=password,
            message="Администратор школы создан",
        )

    def update_school_admin(
        self,
        user_id: int,
        *,
        email: str | None = None,
        password: str | None = None,
        is_active: bool | None = None,
        fields_set: frozenset[str] | None = None,
    ) -> SchoolAdminData:
        user = self.db.get(User, user_id)
        if user is None or user.role != ROLE_SCHOOL_ADMIN:
            raise NotFoundError("Админ школы не найден")

        fields_set = fields_set or frozenset()
        if not fields_set:
            raise BadRequestError("Нечего обновлять")

        if "email" in fields_set and email is not None:
            new_email = str(email).lower().strip()
            clash = self.db.scalars(
                select(User).where(User.email == new_email, User.id != user.id)
            ).first()
            if clash is not None:
                raise BadRequestError("Email уже занят")
            user.email = new_email
        if "password" in fields_set and password:
            user.password_hash = hash_password(password)
        if "is_active" in fields_set and is_active is not None:
            user.is_active = is_active

        self.db.commit()
        self.db.refresh(user)
        return SchoolAdminData(
            id=user.id,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
            password=password if "password" in fields_set else None,
        )
