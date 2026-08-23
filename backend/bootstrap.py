"""Bootstrap first platform admin and default school when DB is empty."""
from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ScheduleSettings, School, User
from app.models.user import ROLE_PLATFORM_ADMIN
from app.services.admin_service import slugify
from backend.security import hash_password

logger = logging.getLogger(__name__)


def ensure_default_school(db: Session) -> School:
    school = db.scalars(select(School).order_by(School.id)).first()
    if school is not None:
        return school
    school = School(name="Школа по умолчанию", slug="default", is_active=True)
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
    logger.info("Created default school id=%s", school.id)
    return school


def bootstrap_admin(db: Session) -> None:
    count = db.scalar(select(func.count()).select_from(User)) or 0
    if count > 0:
        return
    email = Config.BOOTSTRAP_ADMIN_EMAIL
    password = Config.BOOTSTRAP_ADMIN_PASSWORD
    if not email or not password:
        logger.warning(
            "No users and BOOTSTRAP_ADMIN_EMAIL/PASSWORD unset — "
            "set them to create the first platform admin"
        )
        return
    user = User(
        email=email.lower(),
        password_hash=hash_password(password),
        role=ROLE_PLATFORM_ADMIN,
        school_id=None,
        is_active=True,
    )
    db.add(user)
    db.commit()
    logger.info("Bootstrapped platform admin %s", email)
