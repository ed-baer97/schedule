"""CRUD smoke tests for directories already on FastAPI get_db."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.models import (
    Classroom,
    ScheduleCell,
    SchoolClass,
    Shift,
    Subject,
    Teacher,
    TeachingAssignment,
    classroom_subjects,
)
from backend.deps import SessionLocal
from backend.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clear() -> None:
    with SessionLocal() as session:
        # Children before parents — avoids orphan FKs and SQLite id reuse collisions.
        session.execute(delete(ScheduleCell))
        session.execute(delete(TeachingAssignment))
        session.execute(delete(SchoolClass))
        session.execute(delete(Teacher))
        session.execute(delete(classroom_subjects))
        session.execute(delete(Classroom))
        session.execute(delete(Shift))
        session.execute(delete(Subject))
        session.commit()


def test_classroom_crud() -> None:
    created = client.post(
        "/api/classrooms/",
        json={"number": "101", "name": "Математика", "classes_capacity": 1},
    )
    assert created.status_code == 200, created.text
    cid = created.json()["id"]
    assert created.json()["display_name"]
    assert created.json()["subject_ids"] == []
    assert created.json()["subjects"] == []
    assert created.json()["is_exclusive"] is False
    assert created.json()["school_level"] is None
    assert created.json()["teachers"] == []

    listed = client.get("/api/classrooms/")
    assert listed.status_code == 200
    assert any(r["id"] == cid for r in listed.json())

    updated = client.put(
        f"/api/classrooms/{cid}",
        json={"number": "101", "name": "Алгебра", "classes_capacity": 2},
    )
    assert updated.status_code == 200
    assert updated.json()["classes_capacity"] == 2

    deleted = client.delete(f"/api/classrooms/{cid}")
    assert deleted.status_code == 204
    assert client.get(f"/api/classrooms/{cid}").status_code == 404


def test_classroom_subject_pool() -> None:
    subj = client.post(
        "/api/subjects/",
        json={
            "name": "Информатика",
            "color": "#147f78",
            "requires_fixed_classroom": True,
        },
    )
    assert subj.status_code == 200, subj.text
    sid = subj.json()["id"]

    bad = client.post(
        "/api/classrooms/",
        json={"number": "32", "is_exclusive": True},
    )
    assert bad.status_code in (400, 422)

    room = client.post(
        "/api/classrooms/",
        json={
            "number": "32",
            "name": "Инф",
            "subject_ids": [sid],
            "is_exclusive": True,
            "classes_capacity": 1,
        },
    )
    assert room.status_code == 200, room.text
    assert room.json()["subject_ids"] == [sid]
    assert room.json()["is_exclusive"] is True
    assert room.json()["subjects"][0]["name"] == "Информатика"

    listed_subj = client.get("/api/subjects/")
    assert listed_subj.status_code == 200
    row = next(s for s in listed_subj.json() if s["id"] == sid)
    assert any(c["id"] == room.json()["id"] for c in row["classrooms"])


def test_classroom_multiple_teachers() -> None:
    first = client.post("/api/teachers/", json={"full_name": "Иванов И.И."})
    second = client.post("/api/teachers/", json={"full_name": "Петрова П.П."})
    third = client.post("/api/teachers/", json={"full_name": "Сидоров С.С."})
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert third.status_code == 200, third.text
    a_id, b_id, c_id = first.json()["id"], second.json()["id"], third.json()["id"]

    room = client.post(
        "/api/classrooms/",
        json={"number": "12", "name": "Математика", "teacher_ids": [a_id, b_id]},
    )
    assert room.status_code == 200, room.text
    names = [t["full_name"] for t in room.json()["teachers"]]
    assert names == ["Иванов И.И.", "Петрова П.П."]

    other = client.post(
        "/api/classrooms/",
        json={"number": "14", "teacher_ids": [c_id]},
    )
    assert other.status_code == 200, other.text
    other_id = other.json()["id"]

    moved = client.put(
        f"/api/classrooms/{room.json()['id']}",
        json={"teacher_ids": [b_id, c_id]},
    )
    assert moved.status_code == 200, moved.text
    moved_ids = {t["id"] for t in moved.json()["teachers"]}
    assert moved_ids == {b_id, c_id}

    listed = client.get("/api/teachers/")
    assert listed.status_code == 200
    by_id = {t["id"]: t for t in listed.json()}
    assert by_id[a_id]["home_classroom_id"] is None
    assert by_id[b_id]["home_classroom_id"] == room.json()["id"]
    assert by_id[c_id]["home_classroom_id"] == room.json()["id"]

    leftover = client.get(f"/api/classrooms/{other_id}")
    assert leftover.status_code == 200
    assert leftover.json()["teachers"] == []


def test_classroom_multiple_subjects() -> None:
    algebra = client.post("/api/subjects/", json={"name": "Алгебра", "color": "#147f78"})
    geometry = client.post("/api/subjects/", json={"name": "Геометрия", "color": "#c45a42"})
    math = client.post("/api/subjects/", json={"name": "Математика", "color": "#c4842e"})
    rus = client.post("/api/subjects/", json={"name": "Русский язык", "color": "#0e5c57"})
    assert algebra.status_code == 200, algebra.text
    assert geometry.status_code == 200, geometry.text
    assert math.status_code == 200, math.text
    assert rus.status_code == 200, rus.text
    a_id, g_id, m_id = algebra.json()["id"], geometry.json()["id"], math.json()["id"]

    room = client.post(
        "/api/classrooms/",
        json={
            "number": "43",
            "name": "Математика",
            "subject_ids": [a_id, g_id, m_id],
            "is_exclusive": False,
        },
    )
    assert room.status_code == 200, room.text
    names = [s["name"] for s in room.json()["subjects"]]
    assert names == ["Алгебра", "Геометрия", "Математика"]
    assert set(room.json()["subject_ids"]) == {a_id, g_id, m_id}

    listed = client.get("/api/subjects/")
    assert listed.status_code == 200
    by_id = {s["id"]: s for s in listed.json()}
    for sid in (a_id, g_id, m_id):
        assert any(c["id"] == room.json()["id"] for c in by_id[sid]["classrooms"])
    assert all(
        c["id"] != room.json()["id"] for c in by_id[rus.json()["id"]]["classrooms"]
    )

    updated = client.put(
        f"/api/classrooms/{room.json()['id']}",
        json={"subject_ids": [a_id, m_id], "is_exclusive": True},
    )
    assert updated.status_code == 200, updated.text
    assert {s["id"] for s in updated.json()["subjects"]} == {a_id, m_id}
    assert updated.json()["is_exclusive"] is True


def test_shift_and_class_crud() -> None:
    shift = client.post(
        "/api/shifts/",
        json={
            "name": "1 смена",
            "school_level": "elementary",
            "start_lesson": 1,
            "lessons_count": 5,
            "working_days": 5,
            "max_lessons_per_day": 5,
        },
    )
    assert shift.status_code == 200, shift.text
    shift_id = shift.json()["id"]

    cls = client.post(
        "/api/school-classes/",
        json={
            "name": "1А",
            "school_level": "elementary",
            "shift_id": shift_id,
        },
    )
    assert cls.status_code == 200, cls.text
    class_id = cls.json()["id"]
    assert cls.json()["shift"]["name"] == "1 смена"

    batch = client.post(
        "/api/school-classes/batch-shift",
        json={"class_ids": [class_id], "shift_id": None},
    )
    assert batch.status_code == 200, batch.text
    updated = next(c for c in batch.json() if c["id"] == class_id)
    assert updated["shift_id"] is None

    assert client.delete(f"/api/school-classes/{class_id}").status_code == 204
    assert client.delete(f"/api/shifts/{shift_id}").status_code == 204


def test_class_homeroom_teacher() -> None:
    teacher = client.post("/api/teachers/", json={"full_name": "Иванова А.А."})
    assert teacher.status_code == 200, teacher.text
    teacher_id = teacher.json()["id"]

    created = client.post(
        "/api/school-classes/",
        json={
            "name": "2Б",
            "school_level": "elementary",
            "homeroom_teacher_id": teacher_id,
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["homeroom_teacher_id"] == teacher_id
    assert body["homeroom_teacher"]["full_name"] == "Иванова А.А."

    updated = client.put(
        f"/api/school-classes/{body['id']}",
        json={"homeroom_teacher_id": None},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["homeroom_teacher_id"] is None
    assert updated.json()["homeroom_teacher"] is None


def test_teacher_crud_roundtrip() -> None:
    created = client.post(
        "/api/teachers/",
        json={"full_name": "Петров П.П.", "email": "p@example.com"},
    )
    assert created.status_code == 200, created.text
    tid = created.json()["id"]

    updated = client.put(
        f"/api/teachers/{tid}",
        json={"full_name": "Петров Пётр", "email": None, "phone": "123"},
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["full_name"] == "Петров Пётр"
    assert body["phone"] == "123"

    assert client.delete(f"/api/teachers/{tid}").status_code == 204


def test_teacher_load_hours_and_shifts() -> None:
    first = client.post("/api/teachers/", json={"full_name": "Иванов Иван Иванович"})
    second = client.post("/api/teachers/", json={"full_name": "Петрова Анна Сергеевна"})
    idle = client.post("/api/teachers/", json={"full_name": "Сидоров С.С."})
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert idle.status_code == 200, idle.text
    first_id, second_id, idle_id = first.json()["id"], second.json()["id"], idle.json()["id"]

    math = client.post("/api/subjects/", json={"name": "Математика", "color": "#147f78"})
    info = client.post("/api/subjects/", json={"name": "Информатика", "color": "#c45a42"})
    assert math.status_code == 200, math.text
    assert info.status_code == 200, info.text
    math_id, info_id = math.json()["id"], info.json()["id"]

    shift1 = client.post(
        "/api/shifts/",
        json={
            "name": "1 смена",
            "school_level": "elementary",
            "start_lesson": 1,
            "lessons_count": 5,
            "working_days": 5,
            "max_lessons_per_day": 5,
        },
    )
    shift2 = client.post(
        "/api/shifts/",
        json={
            "name": "2 смена",
            "school_level": "secondary",
            "start_lesson": 1,
            "lessons_count": 6,
            "working_days": 5,
            "max_lessons_per_day": 7,
        },
    )
    assert shift1.status_code == 200, shift1.text
    assert shift2.status_code == 200, shift2.text
    shift1_id, shift2_id = shift1.json()["id"], shift2.json()["id"]

    cls_a = client.post(
        "/api/school-classes/",
        json={"name": "1А", "school_level": "elementary", "shift_id": shift1_id},
    )
    cls_b = client.post(
        "/api/school-classes/",
        json={"name": "5А", "school_level": "secondary", "shift_id": shift2_id},
    )
    cls_none = client.post(
        "/api/school-classes/",
        json={"name": "2Б", "school_level": "elementary"},
    )
    assert cls_a.status_code == 200, cls_a.text
    assert cls_b.status_code == 200, cls_b.text
    assert cls_none.status_code == 200, cls_none.text

    a1 = client.post(
        "/api/assignments/",
        json={
            "subject_id": math_id,
            "teacher_id": first_id,
            "class_id": cls_a.json()["id"],
            "hours_per_week": 5,
        },
    )
    a2 = client.post(
        "/api/assignments/",
        json={
            "subject_id": math_id,
            "teacher_id": first_id,
            "class_id": cls_b.json()["id"],
            "hours_per_week": 4,
        },
    )
    a3 = client.post(
        "/api/assignments/",
        json={
            "subject_id": info_id,
            "teacher_id": first_id,
            "class_id": cls_a.json()["id"],
            "hours_per_week": 2,
        },
    )
    a4 = client.post(
        "/api/assignments/",
        json={
            "subject_id": info_id,
            "teacher_id": second_id,
            "class_id": cls_none.json()["id"],
            "hours_per_week": 3,
        },
    )
    assert a1.status_code == 201, a1.text
    assert a2.status_code == 201, a2.text
    assert a3.status_code == 201, a3.text
    assert a4.status_code == 201, a4.text

    listed = client.get("/api/teachers/load")
    assert listed.status_code == 200, listed.text
    by_id = {row["id"]: row for row in listed.json()}

    ivanov = by_id[first_id]
    assert ivanov["full_name"] == "Иванов Иван Иванович"
    assert ivanov["total_hours"] == 11
    subjects = {s["subject_name"]: s["hours"] for s in ivanov["subjects"]}
    assert subjects == {"Информатика": 2, "Математика": 9}
    shift_hours = {s["name"]: s["hours"] for s in ivanov["shifts"]}
    assert shift_hours == {"1 смена": 7, "2 смена": 4}
    assert ivanov["unassigned_shift_hours"] == 0
    assert ivanov["has_classes_without_shift"] is False

    petrova = by_id[second_id]
    assert petrova["total_hours"] == 3
    assert petrova["subjects"][0]["subject_name"] == "Информатика"
    assert petrova["shifts"] == []
    assert petrova["unassigned_shift_hours"] == 3
    assert petrova["has_classes_without_shift"] is True

    sidirov = by_id[idle_id]
    assert sidirov["full_name"] == "Сидоров С.С."
    assert sidirov["subjects"] == []
    assert sidirov["shifts"] == []
    assert sidirov["total_hours"] == 0
    assert sidirov["unassigned_shift_hours"] == 0
    assert sidirov["has_classes_without_shift"] is False


def test_classroom_school_level_roundtrip() -> None:
    created = client.post(
        "/api/classrooms/",
        json={"number": "НШ-11", "school_level": "elementary"},
    )
    assert created.status_code == 200, created.text
    cid = created.json()["id"]
    assert created.json()["school_level"] == "elementary"

    cleared = client.put(f"/api/classrooms/{cid}", json={"school_level": None})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["school_level"] is None

    bad = client.post(
        "/api/classrooms/",
        json={"number": "НШ-bad", "school_level": "primary"},
    )
    assert bad.status_code == 422


def test_classroom_subgroup_only_roundtrip() -> None:
    created = client.post(
        "/api/classrooms/",
        json={"number": "5а", "subgroup_only": True},
    )
    assert created.status_code == 200, created.text
    cid = created.json()["id"]
    assert created.json()["subgroup_only"] is True

    cleared = client.put(f"/api/classrooms/{cid}", json={"subgroup_only": False})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["subgroup_only"] is False


def test_elementary_class_home_tags_general_room() -> None:
    room = client.post("/api/classrooms/", json={"number": "1А-каб"})
    assert room.status_code == 200, room.text
    rid = room.json()["id"]
    assert room.json()["school_level"] is None

    cls = client.post(
        "/api/school-classes/",
        json={
            "name": "1Г",
            "school_level": "elementary",
            "home_classroom_id": rid,
        },
    )
    assert cls.status_code == 200, cls.text
    tagged = client.get(f"/api/classrooms/{rid}")
    assert tagged.status_code == 200
    assert tagged.json()["school_level"] == "elementary"


def test_elementary_class_home_does_not_tag_specialist_room() -> None:
    pe = client.post(
        "/api/subjects/",
        json={"name": "Физкультура", "requires_fixed_classroom": True},
    )
    assert pe.status_code == 200, pe.text
    gym = client.post(
        "/api/classrooms/",
        json={"number": "СЗ-1", "subject_ids": [pe.json()["id"]]},
    )
    assert gym.status_code == 200, gym.text
    gid = gym.json()["id"]

    cls = client.post(
        "/api/school-classes/",
        json={
            "name": "1Д",
            "school_level": "elementary",
            "home_classroom_id": gid,
        },
    )
    assert cls.status_code == 200, cls.text
    still = client.get(f"/api/classrooms/{gid}")
    assert still.status_code == 200
    assert still.json()["school_level"] is None


def test_subject_difficulty_crud_roundtrip() -> None:
    # Default is medium
    created = client.post(
        "/api/subjects/",
        json={"name": "Химия", "color": "#147f78"},
    )
    assert created.status_code == 200, created.text
    sid = created.json()["id"]
    assert created.json()["difficulty"] == "medium"

    # Update to hard
    updated = client.put(
        f"/api/subjects/{sid}",
        json={"difficulty": "hard"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["difficulty"] == "hard"

    # Create explicit easy
    easy_subj = client.post(
        "/api/subjects/",
        json={"name": "ИЗО", "difficulty": "easy"},
    )
    assert easy_subj.status_code == 200, easy_subj.text
    assert easy_subj.json()["difficulty"] == "easy"

