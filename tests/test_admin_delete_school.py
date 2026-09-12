"""Platform admin: delete school cascades tenant data."""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models import (
    Classroom,
    ScheduleCell,
    ScheduleSettings,
    School,
    SchoolClass,
    Shift,
    Subject,
    Teacher,
    TeachingAssignment,
    User,
)
from app.models.user import ROLE_PLATFORM_ADMIN, ROLE_SCHOOL_ADMIN
from app.passwords import hash_password
from app.services.admin_service import AdminService
from app.services.errors import NotFoundError
from backend.deps import SessionLocal, get_current_user
from backend.main import app
from tests.conftest import _override_user_attached

client = TestClient(app)


def test_delete_school_removes_tenant_rows() -> None:
    with SessionLocal() as db:
        school = School(name="To Delete", slug="to-delete-school", is_active=True)
        db.add(school)
        db.flush()
        sid = school.id
        db.add(
            ScheduleSettings(
                school_id=sid,
                school_level="elementary",
                max_lessons_per_subject_per_day=2,
                classroom_mode="class_room",
                elementary_group_subjects_leave=True,
            )
        )
        shift = Shift(
            school_id=sid,
            name="1",
            school_level="elementary",
            start_lesson=1,
            lessons_count=5,
        )
        room = Classroom(school_id=sid, number="101")
        subject = Subject(school_id=sid, name="Math")
        teacher = Teacher(school_id=sid, full_name="T One")
        db.add_all([shift, room, subject, teacher])
        db.flush()
        klass = SchoolClass(
            school_id=sid,
            name="1А",
            grade=1,
            school_level="elementary",
            shift_id=shift.id,
            home_classroom_id=room.id,
            homeroom_teacher_id=teacher.id,
        )
        db.add(klass)
        db.flush()
        teacher.home_classroom_id = room.id
        assignment = TeachingAssignment(
            school_id=sid,
            subject_id=subject.id,
            teacher_id=teacher.id,
            class_id=klass.id,
            hours_per_week=5,
        )
        db.add(assignment)
        db.flush()
        db.add(
            ScheduleCell(
                school_id=sid,
                class_id=klass.id,
                day_of_week=1,
                lesson_number=1,
                assignment_id=assignment.id,
                classroom_id=room.id,
            )
        )
        db.add(
            User(
                email="school-admin-delete-test@example.com",
                password_hash=hash_password("password123"),
                role=ROLE_SCHOOL_ADMIN,
                school_id=sid,
                is_active=True,
            )
        )
        db.commit()

    with SessionLocal() as db:
        AdminService(db).delete_school(sid)

    with SessionLocal() as db:
        assert db.get(School, sid) is None
        assert (
            db.scalar(
                select(func.count())
                .select_from(SchoolClass)
                .where(SchoolClass.school_id == sid)
            )
            == 0
        )
        assert (
            db.scalar(
                select(func.count()).select_from(Teacher).where(Teacher.school_id == sid)
            )
            == 0
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(Classroom)
                .where(Classroom.school_id == sid)
            )
            == 0
        )
        assert (
            db.scalar(
                select(func.count()).select_from(Subject).where(Subject.school_id == sid)
            )
            == 0
        )
        assert (
            db.scalar(
                select(func.count()).select_from(Shift).where(Shift.school_id == sid)
            )
            == 0
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(ScheduleCell)
                .where(ScheduleCell.school_id == sid)
            )
            == 0
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(TeachingAssignment)
                .where(TeachingAssignment.school_id == sid)
            )
            == 0
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(ScheduleSettings)
                .where(ScheduleSettings.school_id == sid)
            )
            == 0
        )
        assert (
            db.scalar(select(func.count()).select_from(User).where(User.school_id == sid))
            == 0
        )


def test_delete_school_not_found() -> None:
    with SessionLocal() as db:
        try:
            AdminService(db).delete_school(9_999_999)
            raise AssertionError("expected NotFoundError")
        except NotFoundError:
            pass


def test_delete_school_api_requires_platform_admin() -> None:
    r = client.delete("/api/admin/schools/1")
    assert r.status_code == 403


def test_delete_school_api_ok() -> None:
    with SessionLocal() as db:
        admin = db.scalars(
            select(User).where(User.email == "platform-admin-delete-test@example.com")
        ).first()
        if admin is None:
            admin = User(
                email="platform-admin-delete-test@example.com",
                password_hash=hash_password("password123"),
                role=ROLE_PLATFORM_ADMIN,
                school_id=None,
                is_active=True,
            )
            db.add(admin)
            db.commit()
            db.refresh(admin)
        admin_id = admin.id
        school = AdminService(db).create_school(name="API Delete Me", slug="api-delete-me")
        school_id = school.id

    def _as_platform_admin() -> User:
        db = SessionLocal()
        user = db.get(User, admin_id)
        assert user is not None
        db.expunge(user)
        db.close()
        return user

    app.dependency_overrides[get_current_user] = _as_platform_admin
    try:
        r = client.delete(f"/api/admin/schools/{school_id}")
        assert r.status_code == 204
        with SessionLocal() as db:
            assert db.get(School, school_id) is None
    finally:
        app.dependency_overrides[get_current_user] = _override_user_attached
