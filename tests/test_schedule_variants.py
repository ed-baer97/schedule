"""Main / temporary / monthly schedule grids and fractional hours."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.models import (
    ScheduleCell,
    ScheduleSettings,
    SchoolClass,
    Shift,
    Subject,
    Teacher,
    TeachingAssignment,
)
from backend.deps import SessionLocal
from backend.main import app
from tests.conftest import TEST_SCHOOL_ID

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clear_db() -> None:
    with SessionLocal() as session:
        for model in (
            ScheduleCell,
            TeachingAssignment,
            ScheduleSettings,
            SchoolClass,
            Shift,
            Subject,
            Teacher,
        ):
            session.execute(delete(model))
        session.commit()


def _seed() -> dict[str, int]:
    with SessionLocal() as session:
        shift = Shift(
            school_id=TEST_SCHOOL_ID,
            name="1 смена",
            school_level="elementary",
            start_lesson=1,
            lessons_count=5,
            working_days=5,
            max_lessons_per_day=5,
        )
        math = Subject(school_id=TEST_SCHOOL_ID, name="Математика")
        extra = Subject(school_id=TEST_SCHOOL_ID, name="Робототехника")
        teacher = Teacher(school_id=TEST_SCHOOL_ID, full_name="Иванов И.И.")
        cls = SchoolClass(
            school_id=TEST_SCHOOL_ID,
            name="1А",
            grade=1,
            school_level="elementary",
        )
        session.add_all([shift, math, extra, teacher, cls])
        session.flush()
        cls.shift_id = shift.id
        weekly = TeachingAssignment(
            school_id=TEST_SCHOOL_ID,
            subject_id=math.id,
            teacher_id=teacher.id,
            class_id=cls.id,
            hours_per_week=2,
        )
        monthly = TeachingAssignment(
            school_id=TEST_SCHOOL_ID,
            subject_id=extra.id,
            teacher_id=teacher.id,
            class_id=cls.id,
            hours_per_week=0.25,
        )
        twice = TeachingAssignment(
            school_id=TEST_SCHOOL_ID,
            subject_id=extra.id,
            teacher_id=teacher.id,
            class_id=cls.id,
            hours_per_week=0.5,
            group_number=2,
        )
        session.add_all([weekly, monthly, twice])
        session.commit()
        return {
            "shift_id": shift.id,
            "class_id": cls.id,
            "weekly_id": weekly.id,
            "monthly_id": monthly.id,
            "twice_id": twice.id,
        }


def test_fractional_hours_not_in_main_grid() -> None:
    ids = _seed()
    r = client.post(
        "/api/schedule/cells",
        json={
            "class_id": ids["class_id"],
            "day_of_week": 1,
            "lesson_number": 1,
            "assignment_id": ids["monthly_id"],
            "classroom_id": None,
        },
    )
    assert r.status_code == 422, r.text
    assert "месячном" in r.text

    choices = client.get(
        f"/api/schedule/assignments-for-class/{ids['class_id']}"
    ).json()["assignments"]
    assert {a["id"] for a in choices} == {ids["weekly_id"]}


def test_copy_main_to_temporary_and_monthly() -> None:
    ids = _seed()
    created = client.post(
        "/api/schedule/cells",
        json={
            "class_id": ids["class_id"],
            "day_of_week": 2,
            "lesson_number": 1,
            "assignment_id": ids["weekly_id"],
            "classroom_id": None,
        },
    )
    assert created.status_code == 201, created.text

    copied = client.post(
        "/api/schedule/copy-from-main",
        json={
            "target_kind": "temporary",
            "school_level": "elementary",
            "shift_id": ids["shift_id"],
        },
    )
    assert copied.status_code == 200, copied.text
    assert copied.json()["count"] == 1

    main = client.get(
        f"/api/schedule/grid?school_level=elementary&shift_id={ids['shift_id']}"
    ).json()
    temp = client.get(
        "/api/schedule/grid?school_level=elementary"
        f"&shift_id={ids['shift_id']}&schedule_kind=temporary"
    ).json()
    assert len(main["cells"]) == 1
    assert len(temp["cells"]) == 1
    assert temp["cells"][0]["id"] != main["cells"][0]["id"]
    assert temp["schedule_kind"] == "temporary"

    all_weeks = client.post(
        "/api/schedule/copy-from-main",
        json={
            "target_kind": "monthly",
            "weeks": [1, 2, 3, 4],
            "school_level": "elementary",
            "shift_id": ids["shift_id"],
        },
    )
    assert all_weeks.status_code == 200, all_weeks.text
    assert all_weeks.json()["count"] == 4

    week1 = client.get(
        "/api/schedule/grid?school_level=elementary"
        f"&shift_id={ids['shift_id']}&schedule_kind=monthly&week_index=1"
    ).json()
    week2 = client.get(
        "/api/schedule/grid?school_level=elementary"
        f"&shift_id={ids['shift_id']}&schedule_kind=monthly&week_index=2"
    ).json()
    assert len(week1["cells"]) == 1
    assert len(week2["cells"]) == 1
    assert week1["cells"][0]["id"] != week2["cells"][0]["id"]
    assert week1["week_index"] == 1


def test_quarter_hour_only_one_monthly_week() -> None:
    ids = _seed()
    first = client.post(
        "/api/schedule/cells",
        json={
            "class_id": ids["class_id"],
            "day_of_week": 3,
            "lesson_number": 2,
            "assignment_id": ids["monthly_id"],
            "classroom_id": None,
            "schedule_kind": "monthly",
            "week_index": 1,
        },
    )
    assert first.status_code == 201, first.text

    second_same_week = client.post(
        "/api/schedule/cells",
        json={
            "class_id": ids["class_id"],
            "day_of_week": 4,
            "lesson_number": 2,
            "assignment_id": ids["monthly_id"],
            "classroom_id": None,
            "schedule_kind": "monthly",
            "week_index": 1,
        },
    )
    assert second_same_week.status_code == 422, second_same_week.text

    other_week = client.post(
        "/api/schedule/cells",
        json={
            "class_id": ids["class_id"],
            "day_of_week": 3,
            "lesson_number": 2,
            "assignment_id": ids["monthly_id"],
            "classroom_id": None,
            "schedule_kind": "monthly",
            "week_index": 2,
        },
    )
    assert other_week.status_code == 422, other_week.text
    assert "уже расставлены" in other_week.text or "вкладку" in other_week.text

    choices = client.get(
        f"/api/schedule/assignments-for-class/{ids['class_id']}"
        "?schedule_kind=monthly&week_index=2"
    ).json()["assignments"]
    ids_left = {a["id"] for a in choices}
    assert ids["monthly_id"] not in ids_left
    assert ids["twice_id"] in ids_left


def test_half_hour_two_monthly_weeks() -> None:
    ids = _seed()
    week1 = client.post(
        "/api/schedule/cells",
        json={
            "class_id": ids["class_id"],
            "day_of_week": 1,
            "lesson_number": 3,
            "assignment_id": ids["twice_id"],
            "classroom_id": None,
            "schedule_kind": "monthly",
            "week_index": 1,
        },
    )
    assert week1.status_code == 201, week1.text
    week2 = client.post(
        "/api/schedule/cells",
        json={
            "class_id": ids["class_id"],
            "day_of_week": 1,
            "lesson_number": 3,
            "assignment_id": ids["twice_id"],
            "classroom_id": None,
            "schedule_kind": "monthly",
            "week_index": 2,
        },
    )
    assert week2.status_code == 201, week2.text
    week3 = client.post(
        "/api/schedule/cells",
        json={
            "class_id": ids["class_id"],
            "day_of_week": 1,
            "lesson_number": 3,
            "assignment_id": ids["twice_id"],
            "classroom_id": None,
            "schedule_kind": "monthly",
            "week_index": 3,
        },
    )
    assert week3.status_code == 422, week3.text

    with SessionLocal() as session:
        cells = list(
            session.scalars(
                select(ScheduleCell).where(
                    ScheduleCell.assignment_id == ids["twice_id"]
                )
            ).all()
        )
        assert len(cells) == 2
        assert {c.week_index for c in cells} == {1, 2}
