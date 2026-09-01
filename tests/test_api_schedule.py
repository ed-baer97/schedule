"""Smoke tests for the newly-migrated schedule / assignments / reports / import endpoints."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.models import (
    Classroom,
    Job,
    ScheduleCell,
    ScheduleSettings,
    SchoolClass,
    Shift,
    Subject,
    Teacher,
    TeachingAssignment,
    classroom_subjects,
)
from backend.deps import SessionLocal
from tests.conftest import TEST_SCHOOL_ID
from backend.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clear_db() -> None:
    with SessionLocal() as session:
        for model in (
            ScheduleCell,
            TeachingAssignment,
            ScheduleSettings,
            Job,
            SchoolClass,
            Shift,
            classroom_subjects,
            Classroom,
            Subject,
            Teacher,
        ):
            session.execute(delete(model))
        session.commit()


def test_schedule_grid_empty() -> None:
    r = client.get("/api/schedule/grid?school_level=elementary")
    assert r.status_code == 200
    body = r.json()
    assert body["school_level"] == "elementary"
    assert body["classes"] == []
    assert body["cells"] == []
    assert body["day_names"][0] == "Понедельник"


def test_schedule_settings_roundtrip() -> None:
    initial = client.get("/api/schedule/settings")
    assert initial.status_code == 200
    body = initial.json()
    assert body == {"elementary": None, "secondary": None}

    upd = client.put(
        "/api/schedule/settings/elementary",
        json={
            "max_lessons_per_subject_per_day": 1,
            "classroom_mode": "teacher_room",
            "elementary_group_subjects_leave": False,
            "pref_teacher_gaps": 8,
            "pref_hard_subjects_early": 9,
            "pref_adjacent_pairs": 2,
            "pref_classroom_stability": 7,
        },
    )
    assert upd.status_code == 200, upd.text
    assert upd.json()["classroom_mode"] == "teacher_room"
    assert upd.json()["pref_teacher_gaps"] == 8
    assert upd.json()["pref_hard_subjects_early"] == 9

    refreshed = client.get("/api/schedule/settings").json()
    assert refreshed["elementary"]["max_lessons_per_subject_per_day"] == 1
    assert refreshed["elementary"]["pref_adjacent_pairs"] == 2
    assert refreshed["elementary"]["pref_classroom_stability"] == 7


def test_auto_page_data_empty() -> None:
    r = client.get("/api/schedule/auto/page-data")
    assert r.status_code == 200
    body = r.json()
    assert body["teachers"] == []
    assert body["classes"] == []
    assert body["shifts_elementary"] == []


def test_assignments_empty_list() -> None:
    r = client.get("/api/assignments/?school_level=elementary")
    assert r.status_code == 200
    assert r.json() == []


def test_assignments_crud_flow() -> None:
    with SessionLocal() as session:
        subject = Subject(school_id=TEST_SCHOOL_ID, name="Математика")
        teacher = Teacher(school_id=TEST_SCHOOL_ID, full_name="Иванов И.И.")
        cls = SchoolClass(school_id=TEST_SCHOOL_ID, name="1А", grade=1, school_level="elementary")
        session.add_all([subject, teacher, cls])
        session.commit()
        subject_id, teacher_id, class_id = subject.id, teacher.id, cls.id

    created = client.post(
        "/api/assignments/",
        json={
            "subject_id": subject_id,
            "teacher_id": teacher_id,
            "class_id": class_id,
            "hours_per_week": 4,
        },
    )
    assert created.status_code == 201, created.text
    aid = created.json()["id"]

    # PATCH /teacher
    patched = client.patch(
        f"/api/assignments/{aid}/teacher", json={"teacher_id": None}
    )
    assert patched.status_code == 200
    assert patched.json()["teacher_id"] is None

    # DELETE
    deleted = client.delete(f"/api/assignments/{aid}")
    assert deleted.status_code == 204
    assert client.get(f"/api/assignments/{aid}").status_code == 404


def test_reports_not_found() -> None:
    assert client.get("/api/reports/class/99999").status_code == 404
    assert client.get("/api/reports/teacher/99999").status_code == 404


def test_import_template_not_found() -> None:
    r = client.get("/api/import/template/does-not-exist")
    assert r.status_code == 404


def test_shift_lesson_times_roundtrip() -> None:
    with SessionLocal() as session:
        shift = Shift(school_id=TEST_SCHOOL_ID, 
            name="Первая",
            school_level="elementary",
            start_lesson=1,
            lessons_count=3,
            working_days=5,
            max_lessons_per_day=5,
            class_hour_day=5,
        )
        session.add(shift)
        session.commit()
        shift_id = shift.id

    body = {
        "common": {
            "1": {"time_start": "08:00", "time_end": "08:45"},
            "2": {"time_start": "08:55", "time_end": "09:40"},
            "3": {"time_start": "", "time_end": ""},
        },
        "class_day": {
            "1": {"time_start": "08:00", "time_end": "08:30"},
        },
    }
    r = client.put(f"/api/shifts/{shift_id}/lesson-times", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    # 4 working days (Mon-Thu) * 2 valid lessons + 1 class-day lesson on Fri = 9
    assert data["inserted"] == 4 * 2 + 1
    assert data["warnings"] == []

    refreshed = client.get(f"/api/shifts/{shift_id}").json()
    times = refreshed["lesson_times"]
    assert any(
        lt["day_of_week"] == 5 and lt["lesson_number"] == 1 and lt["time_start"] == "08:00"
        for lt in times
    )
    assert any(
        lt["day_of_week"] == 1 and lt["lesson_number"] == 2 and lt["time_end"] == "09:40"
        for lt in times
    )


def test_shift_lesson_times_validation_warning() -> None:
    with SessionLocal() as session:
        shift = Shift(school_id=TEST_SCHOOL_ID, 
            name="Бракованная",
            school_level="secondary",
            start_lesson=1,
            lessons_count=2,
            working_days=5,
            max_lessons_per_day=5,
        )
        session.add(shift)
        session.commit()
        shift_id = shift.id

    r = client.put(
        f"/api/shifts/{shift_id}/lesson-times",
        json={
            "common": {
                "1": {"time_start": "09:00", "time_end": "08:00"},
                "2": {"time_start": "09:00", "time_end": ""},
            },
            "class_day": {},
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["inserted"] == 0
    assert any("конец позже начала" in w for w in data["warnings"])
    assert any("укажите оба времени" in w for w in data["warnings"])


def test_class_hour_day_has_fewer_lessons() -> None:
    created = client.post(
        "/api/shifts/",
        json={
            "name": "1 смена КЧ",
            "school_level": "elementary",
            "start_lesson": 1,
            "lessons_count": 6,
            "working_days": 5,
            "max_lessons_per_day": 7,
            "class_hour_day": 1,
            "class_hour_start": "08:00",
            "class_hour_end": "08:20",
            "class_hour_lessons_count": 4,
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["class_hour_day"] == 1
    assert body["class_hour_lessons_count"] == 4
    shift_id = body["id"]

    bells = client.put(
        f"/api/shifts/{shift_id}/lesson-times",
        json={
            "common": {
                "1": {"time_start": "08:00", "time_end": "08:45"},
                "2": {"time_start": "08:55", "time_end": "09:40"},
                "3": {"time_start": "09:50", "time_end": "10:35"},
                "4": {"time_start": "10:45", "time_end": "11:30"},
                "5": {"time_start": "11:40", "time_end": "12:25"},
                "6": {"time_start": "12:35", "time_end": "13:20"},
            },
            "class_day": {
                "1": {"time_start": "08:30", "time_end": "09:15"},
                "2": {"time_start": "09:25", "time_end": "10:10"},
                "3": {"time_start": "10:20", "time_end": "11:05"},
                "4": {"time_start": "11:15", "time_end": "12:00"},
                "5": {"time_start": "12:10", "time_end": "12:55"},
                "6": {"time_start": "13:05", "time_end": "13:50"},
            },
        },
    )
    assert bells.status_code == 200, bells.text
    # 4 ordinary days × 6 lessons + Monday (class-hour) × 4 lessons
    assert bells.json()["inserted"] == 4 * 6 + 4

    times = client.get(f"/api/shifts/{shift_id}").json()["lesson_times"]
    monday = [lt for lt in times if lt["day_of_week"] == 1]
    tuesday = [lt for lt in times if lt["day_of_week"] == 2]
    assert {lt["lesson_number"] for lt in monday} == {1, 2, 3, 4}
    assert {lt["lesson_number"] for lt in tuesday} == {1, 2, 3, 4, 5, 6}


def test_subject_assignments_split_flow() -> None:
    with SessionLocal() as session:
        subject = Subject(school_id=TEST_SCHOOL_ID, name="Английский")
        teacher_a = Teacher(school_id=TEST_SCHOOL_ID, full_name="Алексеева А.А.")
        teacher_b = Teacher(school_id=TEST_SCHOOL_ID, full_name="Борисов Б.Б.")
        cls = SchoolClass(school_id=TEST_SCHOOL_ID, name="5А", grade=5, school_level="secondary")
        session.add_all([subject, teacher_a, teacher_b, cls])
        session.commit()
        session.add(
            TeachingAssignment(school_id=TEST_SCHOOL_ID, 
                subject_id=subject.id,
                class_id=cls.id,
                teacher_id=teacher_a.id,
                hours_per_week=3,
            )
        )
        session.commit()
        subject_id = subject.id
        class_id = cls.id
        a_id, b_id = teacher_a.id, teacher_b.id

    view = client.get(
        f"/api/subjects/{subject_id}/assignments?school_level=secondary"
    )
    assert view.status_code == 200, view.text
    body = view.json()
    assert body["classes"][0]["teacher_ids"] == [a_id]

    save = client.post(
        f"/api/subjects/{subject_id}/assignments",
        json={
            "school_level": "secondary",
            "teacher_ids": [a_id, b_id],
            "selections": {str(class_id): [a_id, b_id]},
        },
    )
    assert save.status_code == 200, save.text
    assert save.json() == {"ok": True, "errors": []}

    with SessionLocal() as session:
        rows = (
            session.query(TeachingAssignment)
            .filter(TeachingAssignment.subject_id == subject_id)
            .order_by(TeachingAssignment.group_number)
            .all()
        )
        assert len(rows) == 2
        assert {r.teacher_id for r in rows} == {a_id, b_id}
        assert {r.group_number for r in rows} == {1, 2}
        assert all(r.hours_per_week == 3 for r in rows)


def test_subject_color_patch() -> None:
    with SessionLocal() as session:
        subject = Subject(school_id=TEST_SCHOOL_ID, name="ИЗО")
        session.add(subject)
        session.commit()
        subject_id = subject.id

    r = client.patch(
        f"/api/subjects/{subject_id}/color",
        json={"color": "#4a7c78"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["display_color"] == "#4a7c78"

    palette = client.get("/api/subjects/meta/color-palette")
    assert palette.status_code == 200
    assert "#147f78" in palette.json()


def test_schedule_cell_crud_and_report() -> None:
    with SessionLocal() as session:
        shift = Shift(school_id=TEST_SCHOOL_ID, 
            name="1 смена",
            school_level="elementary",
            start_lesson=1,
            lessons_count=5,
            working_days=5,
            max_lessons_per_day=5,
        )
        subject = Subject(school_id=TEST_SCHOOL_ID, name="Математика")
        teacher = Teacher(school_id=TEST_SCHOOL_ID, full_name="Сидоров С.С.")
        cls = SchoolClass(school_id=TEST_SCHOOL_ID, name="1Б", grade=1, school_level="elementary")
        session.add_all([shift, subject, teacher, cls])
        session.flush()
        cls.shift_id = shift.id
        assignment = TeachingAssignment(school_id=TEST_SCHOOL_ID, 
            subject_id=subject.id,
            teacher_id=teacher.id,
            class_id=cls.id,
            hours_per_week=4,
        )
        session.add(assignment)
        session.commit()
        class_id, assignment_id, teacher_id = cls.id, assignment.id, teacher.id

    created = client.post(
        "/api/schedule/cells",
        json={
            "class_id": class_id,
            "day_of_week": 1,
            "lesson_number": 1,
            "assignment_id": assignment_id,
        },
    )
    assert created.status_code == 201, created.text
    cell_id = created.json()["id"]
    assert created.json()["subject_name"] == "Математика"

    grid = client.get("/api/schedule/grid?school_level=elementary")
    assert grid.status_code == 200
    assert any(c["id"] == cell_id for c in grid.json()["cells"])

    moved = client.patch(
        f"/api/schedule/cells/{cell_id}",
        json={"day_of_week": 2, "lesson_number": 2},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["day_of_week"] == 2

    report = client.get(f"/api/reports/class/{class_id}")
    assert report.status_code == 200
    assert len(report.json()["cells"]) == 1

    xlsx = client.get(f"/api/reports/export/class/{class_id}")
    assert xlsx.status_code == 200
    assert "spreadsheetml" in xlsx.headers.get("content-type", "")

    teacher_xlsx = client.get(f"/api/reports/export/teacher/{teacher_id}")
    assert teacher_xlsx.status_code == 200

    assert client.delete(f"/api/schedule/cells/{cell_id}").status_code == 204
    assert client.get("/api/schedule/grid?school_level=elementary").json()["cells"] == []


def test_explain_slot_without_qwen_key() -> None:
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
        subject = Subject(school_id=TEST_SCHOOL_ID, name="Математика")
        teacher = Teacher(school_id=TEST_SCHOOL_ID, full_name="Сидоров С.С.")
        cls = SchoolClass(
            school_id=TEST_SCHOOL_ID, name="1Б", grade=1, school_level="elementary"
        )
        session.add_all([shift, subject, teacher, cls])
        session.flush()
        cls.shift_id = shift.id
        assignment = TeachingAssignment(
            school_id=TEST_SCHOOL_ID,
            subject_id=subject.id,
            teacher_id=teacher.id,
            class_id=cls.id,
            hours_per_week=4,
        )
        session.add(assignment)
        session.commit()
        assignment_id = assignment.id

    explained = client.post(
        "/api/schedule/explain",
        json={
            "assignment_id": assignment_id,
            "day_of_week": 1,
            "lesson_number": 1,
        },
    )
    assert explained.status_code == 200, explained.text
    body = explained.json()
    assert body["allowed"] is True
    assert body["llm_used"] is False
    assert body["text"]
    assert "Математика" in body["text"]


def test_repair_enqueue_returns_202() -> None:
    queued = client.post(
        "/api/schedule/repair",
        json={"school_level": "elementary"},
    )
    assert queued.status_code == 202, queued.text
    assert "job_id" in queued.json()


def test_subject_assignments_too_many_teachers() -> None:
    with SessionLocal() as session:
        subject = Subject(school_id=TEST_SCHOOL_ID, name="История")
        teachers = [Teacher(school_id=TEST_SCHOOL_ID, full_name=f"T{i}") for i in range(3)]
        cls = SchoolClass(school_id=TEST_SCHOOL_ID, name="7А", grade=7, school_level="secondary")
        session.add_all([subject, *teachers, cls])
        session.commit()
        session.add(
            TeachingAssignment(school_id=TEST_SCHOOL_ID, 
                subject_id=subject.id,
                class_id=cls.id,
                teacher_id=teachers[0].id,
                hours_per_week=2,
            )
        )
        session.commit()
        subject_id = subject.id
        class_id = cls.id
        tids = [t.id for t in teachers]

    r = client.post(
        f"/api/subjects/{subject_id}/assignments",
        json={
            "school_level": "secondary",
            "teacher_ids": tids,
            "selections": {str(class_id): tids},
        },
    )
    assert r.status_code == 200
    res = r.json()
    assert res["ok"] is False
    assert any("максимум 2 учителя" in e for e in res["errors"])


def _seed_two_classes_one_teacher() -> dict[str, int]:
    with SessionLocal() as session:
        shift = Shift(school_id=TEST_SCHOOL_ID, 
            name="1 смена",
            school_level="elementary",
            start_lesson=1,
            lessons_count=5,
            working_days=5,
            max_lessons_per_day=5,
        )
        math = Subject(school_id=TEST_SCHOOL_ID, name="Математика")
        rus = Subject(school_id=TEST_SCHOOL_ID, name="Русский")
        teacher = Teacher(school_id=TEST_SCHOOL_ID, full_name="Петров П.П.")
        other = Teacher(school_id=TEST_SCHOOL_ID, full_name="Сидорова С.С.")
        c1 = SchoolClass(school_id=TEST_SCHOOL_ID, name="1А", grade=1, school_level="elementary")
        c2 = SchoolClass(school_id=TEST_SCHOOL_ID, name="1Б", grade=1, school_level="elementary")
        session.add_all([shift, math, rus, teacher, other, c1, c2])
        session.flush()
        c1.shift_id = shift.id
        c2.shift_id = shift.id
        a1 = TeachingAssignment(school_id=TEST_SCHOOL_ID, 
            subject_id=math.id,
            teacher_id=teacher.id,
            class_id=c1.id,
            hours_per_week=4,
        )
        a2 = TeachingAssignment(school_id=TEST_SCHOOL_ID, 
            subject_id=math.id,
            teacher_id=teacher.id,
            class_id=c2.id,
            hours_per_week=4,
        )
        a3 = TeachingAssignment(school_id=TEST_SCHOOL_ID, 
            subject_id=rus.id,
            teacher_id=other.id,
            class_id=c1.id,
            hours_per_week=1,
        )
        session.add_all([a1, a2, a3])
        session.commit()
        return {
            "c1": c1.id,
            "c2": c2.id,
            "a1": a1.id,
            "a2": a2.id,
            "a3": a3.id,
            "shift": shift.id,
        }


def test_manual_cell_teacher_conflict_returns_reason() -> None:
    ids = _seed_two_classes_one_teacher()
    first = client.post(
        "/api/schedule/cells",
        json={
            "class_id": ids["c1"],
            "day_of_week": 1,
            "lesson_number": 1,
            "assignment_id": ids["a1"],
        },
    )
    assert first.status_code == 201, first.text

    conflict = client.post(
        "/api/schedule/cells",
        json={
            "class_id": ids["c2"],
            "day_of_week": 1,
            "lesson_number": 1,
            "assignment_id": ids["a2"],
        },
    )
    assert conflict.status_code == 422, conflict.text
    errors = conflict.json()["detail"]["errors"]
    assert any(
        "Петров" in e and "занят" in e and "1А" in e and "Понедельник" in e
        for e in errors
    )


def test_manual_cell_same_bells_different_day_is_free() -> None:
    ids = _seed_two_classes_one_teacher()
    bells = client.put(
        f"/api/shifts/{ids['shift']}/lesson-times",
        json={
            "common": {"1": {"time_start": "08:00", "time_end": "08:45"}},
            "class_day": {},
        },
    )
    assert bells.status_code == 200, bells.text

    monday = client.post(
        "/api/schedule/cells",
        json={
            "class_id": ids["c1"],
            "day_of_week": 1,
            "lesson_number": 1,
            "assignment_id": ids["a1"],
        },
    )
    assert monday.status_code == 201, monday.text

    explained = client.post(
        "/api/schedule/explain",
        json={
            "assignment_id": ids["a2"],
            "day_of_week": 2,
            "lesson_number": 1,
        },
    )
    assert explained.status_code == 200, explained.text
    assert explained.json()["allowed"] is True

    tuesday = client.post(
        "/api/schedule/cells",
        json={
            "class_id": ids["c2"],
            "day_of_week": 2,
            "lesson_number": 1,
            "assignment_id": ids["a2"],
        },
    )
    assert tuesday.status_code == 201, tuesday.text


def test_assignments_for_class_omits_occupied_classroom() -> None:
    with SessionLocal() as session:
        shift = Shift(
            school_id=TEST_SCHOOL_ID,
            name="1 смена",
            school_level="secondary",
            start_lesson=1,
            lessons_count=5,
            working_days=5,
            max_lessons_per_day=5,
        )
        math = Subject(school_id=TEST_SCHOOL_ID, name="Математика")
        t1 = Teacher(school_id=TEST_SCHOOL_ID, full_name="Попов В.Г.")
        t2 = Teacher(school_id=TEST_SCHOOL_ID, full_name="Баер Э.В.")
        c1 = SchoolClass(
            school_id=TEST_SCHOOL_ID, name="6А", grade=6, school_level="secondary"
        )
        c2 = SchoolClass(
            school_id=TEST_SCHOOL_ID, name="7Б", grade=7, school_level="secondary"
        )
        room = Classroom(school_id=TEST_SCHOOL_ID, number="45", name="Математика")
        gym = Classroom(
            school_id=TEST_SCHOOL_ID, number="СЗ", name="Спортзал", classes_capacity=2
        )
        session.add_all([shift, math, t1, t2, c1, c2, room, gym])
        session.flush()
        c1.shift_id = shift.id
        c2.shift_id = shift.id
        a1 = TeachingAssignment(
            school_id=TEST_SCHOOL_ID,
            subject_id=math.id,
            teacher_id=t1.id,
            class_id=c1.id,
            hours_per_week=4,
        )
        a2 = TeachingAssignment(
            school_id=TEST_SCHOOL_ID,
            subject_id=math.id,
            teacher_id=t2.id,
            class_id=c2.id,
            hours_per_week=4,
        )
        session.add_all([a1, a2])
        session.commit()
        ids = {
            "c1": c1.id,
            "c2": c2.id,
            "a1": a1.id,
            "room": room.id,
            "gym": gym.id,
        }

    placed = client.post(
        "/api/schedule/cells",
        json={
            "class_id": ids["c1"],
            "day_of_week": 1,
            "lesson_number": 2,
            "assignment_id": ids["a1"],
            "classroom_id": ids["room"],
        },
    )
    assert placed.status_code == 201, placed.text

    busy = client.get(
        f"/api/schedule/assignments-for-class/{ids['c2']}"
        "?day_of_week=1&lesson_number=2"
    )
    assert busy.status_code == 200, busy.text
    busy_ids = {c["id"] for c in busy.json()["classrooms"]}
    assert ids["room"] not in busy_ids
    assert ids["gym"] in busy_ids

    free = client.get(
        f"/api/schedule/assignments-for-class/{ids['c2']}"
        "?day_of_week=2&lesson_number=2"
    )
    assert free.status_code == 200, free.text
    free_ids = {c["id"] for c in free.json()["classrooms"]}
    assert ids["room"] in free_ids


def test_manual_cell_class_conflict_returns_reason() -> None:
    ids = _seed_two_classes_one_teacher()
    first = client.post(
        "/api/schedule/cells",
        json={
            "class_id": ids["c1"],
            "day_of_week": 1,
            "lesson_number": 2,
            "assignment_id": ids["a1"],
        },
    )
    assert first.status_code == 201, first.text

    conflict = client.post(
        "/api/schedule/cells",
        json={
            "class_id": ids["c1"],
            "day_of_week": 1,
            "lesson_number": 2,
            "assignment_id": ids["a3"],
        },
    )
    assert conflict.status_code == 422, conflict.text
    errors = conflict.json()["detail"]["errors"]
    assert any("Класс уже занят" in e and "Математика" in e for e in errors)


def test_manual_cell_hours_exhausted_returns_reason() -> None:
    ids = _seed_two_classes_one_teacher()
    first = client.post(
        "/api/schedule/cells",
        json={
            "class_id": ids["c1"],
            "day_of_week": 1,
            "lesson_number": 3,
            "assignment_id": ids["a3"],
        },
    )
    assert first.status_code == 201, first.text

    extra = client.post(
        "/api/schedule/cells",
        json={
            "class_id": ids["c1"],
            "day_of_week": 2,
            "lesson_number": 3,
            "assignment_id": ids["a3"],
        },
    )
    assert extra.status_code == 422, extra.text
    errors = extra.json()["detail"]["errors"]
    assert any("уже расставлены" in e and "Русский" in e for e in errors)


def _add_general_classroom(session, number: str = "101") -> Classroom:
    room = Classroom(
        school_id=TEST_SCHOOL_ID,
        number=number,
        classes_capacity=1,
    )
    session.add(room)
    return room


def _seed_shift2_math_teacher(
    n_classes: int = 6, hours: int = 5, *, with_classroom: bool = True
) -> dict[str, int]:
    """One teacher, N classes × `hours` in a 5×6 second-shift grid (exactly N*hours slots)."""
    with SessionLocal() as session:
        shift = Shift(school_id=TEST_SCHOOL_ID,
            name="2 смена",
            school_level="secondary",
            start_lesson=1,
            lessons_count=6,
            working_days=5,
            max_lessons_per_day=7,
        )
        math = Subject(school_id=TEST_SCHOOL_ID, name="Математика")
        teacher = Teacher(school_id=TEST_SCHOOL_ID, full_name="Баер Эдуард Викторович")
        session.add_all([shift, math, teacher])
        session.flush()
        classes = []
        assignments = []
        for i in range(n_classes):
            cls = SchoolClass(school_id=TEST_SCHOOL_ID,
                name=f"5{chr(ord('А') + i)}",
                grade=5,
                school_level="secondary",
                shift_id=shift.id,
            )
            session.add(cls)
            session.flush()
            classes.append(cls)
            assignments.append(
                TeachingAssignment(school_id=TEST_SCHOOL_ID,
                    subject_id=math.id,
                    teacher_id=teacher.id,
                    class_id=cls.id,
                    hours_per_week=hours,
                )
            )
        session.add_all(assignments)
        session.add(
            ScheduleSettings(school_id=TEST_SCHOOL_ID,
                school_level="secondary",
                max_lessons_per_subject_per_day=2,
                classroom_mode="class_room",
                elementary_group_subjects_leave=True,
            )
        )
        room = _add_general_classroom(session) if with_classroom else None
        session.commit()
        return {
            "teacher_id": teacher.id,
            "shift_id": shift.id,
            "class_ids": [c.id for c in classes],
            "assignment_ids": [a.id for a in assignments],
            "classroom_id": room.id if room is not None else None,
        }


def _same_day_pair_stats(teacher_id: int) -> tuple[int, int]:
    """Return (contiguous same-day blocks, split same-day blocks) for a teacher."""
    from collections import defaultdict

    with SessionLocal() as session:
        cells = (
            session.query(ScheduleCell)
            .join(TeachingAssignment)
            .filter(TeachingAssignment.teacher_id == teacher_id)
            .all()
        )
        by: dict[tuple[int, int], list[int]] = defaultdict(list)
        for cell in cells:
            by[(cell.class_id, cell.day_of_week)].append(cell.lesson_number)
        adjacent = 0
        split = 0
        for lessons in by.values():
            if len(lessons) < 2:
                continue
            ordered = sorted(lessons)
            if ordered[-1] - ordered[0] == len(ordered) - 1:
                adjacent += 1
            else:
                split += 1
        return adjacent, split


def test_teacher_ladder_fits_30_hours_on_empty_grid() -> None:
    ids = _seed_shift2_math_teacher()
    with SessionLocal() as session:
        from app.services.assignment_hours import remaining_for
        from app.services.auto_scheduler import AutoScheduler

        result = AutoScheduler(session, school_id=TEST_SCHOOL_ID).schedule_by_teacher_ladder_result(
            ids["teacher_id"], "secondary"
        )
        remaining = sum(
            remaining_for(a)
            for a in session.query(TeachingAssignment).filter(
                TeachingAssignment.teacher_id == ids["teacher_id"]
            )
        )
    assert remaining == 0, result
    assert result["count"] == 30
    with SessionLocal() as session:
        cells = (
            session.query(ScheduleCell)
            .filter(ScheduleCell.assignment_id.in_(ids["assignment_ids"]))
            .all()
        )
        assert cells
        assert all(c.classroom_id is not None for c in cells)
    adjacent, split = _same_day_pair_stats(ids["teacher_id"])
    assert split == 0, (adjacent, split)
    assert adjacent == 12, (adjacent, split)


def test_teacher_ladder_relocates_clustered_leftover_hour() -> None:
    """Last class has 4 of 5 hours on Thu/Fri; only Fri-6 is free — must shift another lesson."""
    ids = _seed_shift2_math_teacher()
    class_ids = ids["class_ids"]
    assignment_ids = ids["assignment_ids"]
    # Clustered packing that leaves Fri lesson 6 empty and 5Е (last) needing 1 more hour.
    # C0: Mon1-2 Tue1-2 Wed1 | C1: Mon3-4 Tue3-4 Wed2 | C2: Mon5-6 Tue5-6 Wed3
    # C3: Wed4-5 Thu1-2 Fri1 | C4: Wed6 Thu3-4 Fri2-3 | C5: Thu5-6 Fri4-5 (4h)
    layout = [
        (0, [(1, 1), (1, 2), (2, 1), (2, 2), (3, 1)]),
        (1, [(1, 3), (1, 4), (2, 3), (2, 4), (3, 2)]),
        (2, [(1, 5), (1, 6), (2, 5), (2, 6), (3, 3)]),
        (3, [(3, 4), (3, 5), (4, 1), (4, 2), (5, 1)]),
        (4, [(3, 6), (4, 3), (4, 4), (5, 2), (5, 3)]),
        (5, [(4, 5), (4, 6), (5, 4), (5, 5)]),
    ]
    with SessionLocal() as session:
        for idx, slots in layout:
            for day, lesson in slots:
                session.add(
                    ScheduleCell(school_id=TEST_SCHOOL_ID, 
                        class_id=class_ids[idx],
                        day_of_week=day,
                        lesson_number=lesson,
                        assignment_id=assignment_ids[idx],
                    )
                )
        session.commit()

    with SessionLocal() as session:
        from app.services.assignment_hours import remaining_for
        from app.services.auto_scheduler import AutoScheduler

        result = AutoScheduler(session, school_id=TEST_SCHOOL_ID).schedule_by_teacher_ladder_result(
            ids["teacher_id"], "secondary"
        )
        session.expire_all()
        last = session.get(TeachingAssignment, assignment_ids[5])
        remaining = sum(
            remaining_for(a)
            for a in session.query(TeachingAssignment).filter(
                TeachingAssignment.teacher_id == ids["teacher_id"]
            )
        )
        assert last is not None
        assert remaining_for(last) == 0, result
        assert remaining == 0, result


def test_cp_sat_two_phase_fills_small_shift() -> None:
    pytest.importorskip("ortools")
    ids = _seed_shift2_math_teacher(n_classes=2, hours=2)
    with SessionLocal() as session:
        from app.services.assignment_hours import remaining_for
        from app.services.auto_scheduler import AutoScheduler

        result = AutoScheduler(session, school_id=TEST_SCHOOL_ID).auto_schedule_all_result(
            school_level="secondary",
            shift_id=ids["shift_id"],
            time_limit_sec=15.0,
            random_seed=1,
        )
        remaining = sum(
            remaining_for(a)
            for a in session.query(TeachingAssignment).filter(
                TeachingAssignment.id.in_(ids["assignment_ids"])
            )
        )
    assert result.get("type") == "done", result
    assert result.get("cp_sat_status") in ("OPTIMAL", "FEASIBLE"), result
    assert remaining == 0, result
    assert result.get("count") == 4
    with SessionLocal() as session:
        cells = (
            session.query(ScheduleCell)
            .filter(ScheduleCell.class_id.in_(ids["class_ids"]))
            .all()
        )
        by: dict[tuple[int, int], list[int]] = {}
        for cell in cells:
            by.setdefault((cell.class_id, cell.day_of_week), []).append(cell.lesson_number)
        for lessons in by.values():
            occupied = sorted(set(lessons))
            assert occupied[0] == 1, occupied
            assert occupied[-1] - occupied[0] + 1 == len(occupied), occupied
        assert all(cell.classroom_id is not None for cell in cells)


def _set_pref_adjacent_pairs(value: int, school_level: str = "secondary") -> None:
    with SessionLocal() as session:
        row = (
            session.query(ScheduleSettings)
            .filter_by(school_id=TEST_SCHOOL_ID, school_level=school_level)
            .one()
        )
        row.pref_adjacent_pairs = value
        session.commit()


def _assignment_day_lessons(assignment_id: int) -> list[list[int]]:
    with SessionLocal() as session:
        cells = (
            session.query(ScheduleCell)
            .filter(ScheduleCell.assignment_id == assignment_id)
            .all()
        )
        by: dict[int, list[int]] = {}
        for cell in cells:
            by.setdefault(cell.day_of_week, []).append(cell.lesson_number)
        return [sorted(v) for _, v in sorted(by.items())]


def test_cp_sat_hard_pairs_packs_even_hours_as_doubles() -> None:
    pytest.importorskip("ortools")
    ids = _seed_shift2_math_teacher(n_classes=1, hours=6)
    _set_pref_adjacent_pairs(10)
    with SessionLocal() as session:
        from app.services.auto_scheduler import AutoScheduler

        result = AutoScheduler(session, school_id=TEST_SCHOOL_ID).auto_schedule_all_result(
            school_level="secondary",
            shift_id=ids["shift_id"],
            time_limit_sec=15.0,
            random_seed=1,
        )
    assert result.get("type") == "done", result
    groups = _assignment_day_lessons(ids["assignment_ids"][0])
    assert [len(g) for g in groups] == [2, 2, 2], groups
    for g in groups:
        assert g[-1] - g[0] == len(g) - 1, g


def test_cp_sat_hard_pairs_odd_hours_one_singleton() -> None:
    pytest.importorskip("ortools")
    ids = _seed_shift2_math_teacher(n_classes=1, hours=5)
    _set_pref_adjacent_pairs(10)
    with SessionLocal() as session:
        from app.services.auto_scheduler import AutoScheduler

        result = AutoScheduler(session, school_id=TEST_SCHOOL_ID).auto_schedule_all_result(
            school_level="secondary",
            shift_id=ids["shift_id"],
            time_limit_sec=15.0,
            random_seed=1,
        )
    assert result.get("type") == "done", result
    groups = _assignment_day_lessons(ids["assignment_ids"][0])
    sizes = sorted(len(g) for g in groups)
    assert sizes == [1, 2, 2], groups
    for g in groups:
        if len(g) == 2:
            assert g[1] == g[0] + 1, g


def test_cp_sat_same_day_pair_is_consecutive_without_max_slider() -> None:
    """Default slider 5: 6h on 5 days needs at least one double; it must not sandwich another lesson."""
    pytest.importorskip("ortools")
    ids = _seed_shift2_math_teacher(n_classes=1, hours=6)
    with SessionLocal() as session:
        from app.services.auto_scheduler import AutoScheduler

        result = AutoScheduler(session, school_id=TEST_SCHOOL_ID).auto_schedule_all_result(
            school_level="secondary",
            shift_id=ids["shift_id"],
            time_limit_sec=15.0,
            random_seed=1,
        )
    assert result.get("type") == "done", result
    groups = _assignment_day_lessons(ids["assignment_ids"][0])
    assert sum(len(g) for g in groups) == 6, groups
    assert any(len(g) == 2 for g in groups), groups
    for g in groups:
        if len(g) >= 2:
            assert g[-1] - g[0] == len(g) - 1, g


def test_cp_sat_paired_lessons_keep_same_classroom() -> None:
    """Two equal general rooms: a same-day double should not hop cabinets."""
    pytest.importorskip("ortools")
    ids = _seed_shift2_math_teacher(n_classes=1, hours=2)
    with SessionLocal() as session:
        _add_general_classroom(session, "102")
        session.commit()
        from app.services.auto_scheduler import AutoScheduler

        result = AutoScheduler(session, school_id=TEST_SCHOOL_ID).auto_schedule_all_result(
            school_level="secondary",
            shift_id=ids["shift_id"],
            time_limit_sec=15.0,
            random_seed=1,
        )
        cells = (
            session.query(ScheduleCell)
            .filter(ScheduleCell.assignment_id == ids["assignment_ids"][0])
            .all()
        )
    assert result.get("type") == "done", result
    assert len(cells) == 2, result
    lessons = sorted(c.lesson_number for c in cells)
    assert lessons[1] == lessons[0] + 1, lessons
    assert cells[0].day_of_week == cells[1].day_of_week
    assert cells[0].classroom_id is not None
    assert cells[0].classroom_id == cells[1].classroom_id


def test_teacher_ladder_paired_lessons_keep_same_classroom() -> None:
    ids = _seed_shift2_math_teacher(n_classes=1, hours=2)
    with SessionLocal() as session:
        _add_general_classroom(session, "102")
        session.commit()
        from app.services.auto_scheduler import AutoScheduler

        result = AutoScheduler(session, school_id=TEST_SCHOOL_ID).schedule_by_teacher_ladder_result(
            ids["teacher_id"], "secondary"
        )
        cells = (
            session.query(ScheduleCell)
            .filter(ScheduleCell.assignment_id == ids["assignment_ids"][0])
            .all()
        )
    assert result["count"] == 2, result
    assert len(cells) == 2
    assert cells[0].classroom_id is not None
    assert cells[0].classroom_id == cells[1].classroom_id


def test_manual_cell_split_pair_returns_reason() -> None:
    ids = _seed_two_classes_one_teacher()
    first = client.post(
        "/api/schedule/cells",
        json={
            "class_id": ids["c1"],
            "day_of_week": 1,
            "lesson_number": 1,
            "assignment_id": ids["a1"],
        },
    )
    assert first.status_code == 201, first.text

    split = client.post(
        "/api/schedule/cells",
        json={
            "class_id": ids["c1"],
            "day_of_week": 1,
            "lesson_number": 3,
            "assignment_id": ids["a1"],
        },
    )
    assert split.status_code == 422, split.text
    errors = split.json()["detail"]["errors"]
    assert any("подряд" in e and "Математика" in e for e in errors)

    adjacent = client.post(
        "/api/schedule/cells",
        json={
            "class_id": ids["c1"],
            "day_of_week": 1,
            "lesson_number": 2,
            "assignment_id": ids["a1"],
        },
    )
    assert adjacent.status_code == 201, adjacent.text


def _seed_secondary_grade_bands() -> dict:
    """One 5th-grade and one 7th-grade class in the same secondary shift."""
    with SessionLocal() as session:
        shift = Shift(
            school_id=TEST_SCHOOL_ID,
            name="1 смена",
            school_level="secondary",
            start_lesson=1,
            lessons_count=6,
            working_days=5,
            max_lessons_per_day=7,
        )
        math = Subject(school_id=TEST_SCHOOL_ID, name="Математика")
        teacher = Teacher(school_id=TEST_SCHOOL_ID, full_name="Учитель параллелей")
        session.add_all([shift, math, teacher])
        session.flush()
        c5 = SchoolClass(
            school_id=TEST_SCHOOL_ID,
            name="5А",
            grade=5,
            school_level="secondary",
            shift_id=shift.id,
        )
        c7 = SchoolClass(
            school_id=TEST_SCHOOL_ID,
            name="7А",
            grade=7,
            school_level="secondary",
            shift_id=shift.id,
        )
        session.add_all([c5, c7])
        session.flush()
        a5 = TeachingAssignment(
            school_id=TEST_SCHOOL_ID,
            subject_id=math.id,
            teacher_id=teacher.id,
            class_id=c5.id,
            hours_per_week=2,
        )
        a7 = TeachingAssignment(
            school_id=TEST_SCHOOL_ID,
            subject_id=math.id,
            teacher_id=teacher.id,
            class_id=c7.id,
            hours_per_week=2,
        )
        session.add_all([a5, a7])
        session.add(
            ScheduleSettings(
                school_id=TEST_SCHOOL_ID,
                school_level="secondary",
                max_lessons_per_subject_per_day=2,
                classroom_mode="class_room",
                elementary_group_subjects_leave=True,
            )
        )
        room = _add_general_classroom(session)
        session.commit()
        return {
            "shift_id": shift.id,
            "class_ids": [c5.id, c7.id],
            "assignment_ids": [a5.id, a7.id],
            "classroom_id": room.id,
        }


def test_cp_sat_grade_bands_fills_5_then_7() -> None:
    pytest.importorskip("ortools")
    ids = _seed_secondary_grade_bands()
    with SessionLocal() as session:
        from app.services.assignment_hours import remaining_for
        from app.services.auto_scheduler import AutoScheduler

        result = AutoScheduler(session, school_id=TEST_SCHOOL_ID).auto_schedule_all_result(
            school_level="secondary",
            shift_id=ids["shift_id"],
            time_limit_sec=15.0,
            random_seed=1,
            split="grade_bands",
        )
        remaining = sum(
            remaining_for(a)
            for a in session.query(TeachingAssignment).filter(
                TeachingAssignment.id.in_(ids["assignment_ids"])
            )
        )
    assert result.get("type") == "done", result
    assert result.get("chunks") == 2, result
    assert result.get("cp_sat_status") in ("OPTIMAL", "FEASIBLE"), result
    assert remaining == 0, result
    assert result.get("count") == 4


def test_cp_sat_grade_bands_noop_when_all_same_parallel() -> None:
    pytest.importorskip("ortools")
    ids = _seed_shift2_math_teacher(n_classes=2, hours=2)
    with SessionLocal() as session:
        from app.services.auto_scheduler import AutoScheduler

        result = AutoScheduler(session, school_id=TEST_SCHOOL_ID).auto_schedule_all_result(
            school_level="secondary",
            shift_id=ids["shift_id"],
            time_limit_sec=15.0,
            random_seed=1,
            split="grade_bands",
        )
    assert result.get("type") == "done", result
    assert result.get("chunks") is None, result
    assert result.get("count") == 4


def test_cp_sat_stops_when_teacher_hours_exceed_shift_slots() -> None:
    """6 classes × 6h = 36h for one teacher vs 5×6 = 30 shift slots."""
    ids = _seed_shift2_math_teacher(n_classes=6, hours=6)
    with SessionLocal() as session:
        from app.services.auto_scheduler import AutoScheduler

        before = session.query(ScheduleCell).count()
        result = AutoScheduler(session, school_id=TEST_SCHOOL_ID).auto_schedule_all_result(
            school_level="secondary",
            shift_id=ids["shift_id"],
            time_limit_sec=5.0,
            random_seed=1,
        )
        after = session.query(ScheduleCell).count()
    assert result.get("type") == "error", result
    assert result.get("cp_sat_status") == "INFEASIBLE", result
    blob = (result.get("message") or "") + " ".join(
        d.get("reason", "") for d in (result.get("diagnostics") or [])
    )
    assert "36" in blob and "30" in blob, blob
    assert "Баер" in blob, blob
    assert after == before


def test_cp_sat_infeasible_without_classrooms() -> None:
    pytest.importorskip("ortools")
    ids = _seed_shift2_math_teacher(n_classes=1, hours=2, with_classroom=False)
    with SessionLocal() as session:
        from app.services.auto_scheduler import AutoScheduler

        before = session.query(ScheduleCell).count()
        result = AutoScheduler(session, school_id=TEST_SCHOOL_ID).auto_schedule_all_result(
            school_level="secondary",
            shift_id=ids["shift_id"],
            time_limit_sec=5.0,
            random_seed=1,
        )
        after = session.query(ScheduleCell).count()
    assert result.get("type") == "error", result
    assert result.get("cp_sat_status") == "INFEASIBLE", result
    blob = (result.get("message") or "") + " ".join(
        d.get("reason", "") for d in (result.get("diagnostics") or [])
    )
    assert "кабинет" in blob.lower(), blob
    assert after == before


def test_teacher_ladder_places_nothing_without_classroom() -> None:
    ids = _seed_shift2_math_teacher(n_classes=1, hours=2, with_classroom=False)
    with SessionLocal() as session:
        from app.services.assignment_hours import remaining_for
        from app.services.auto_scheduler import AutoScheduler

        result = AutoScheduler(session, school_id=TEST_SCHOOL_ID).schedule_by_teacher_ladder_result(
            ids["teacher_id"], "secondary"
        )
        remaining = sum(
            remaining_for(a)
            for a in session.query(TeachingAssignment).filter(
                TeachingAssignment.teacher_id == ids["teacher_id"]
            )
        )
        cells = session.query(ScheduleCell).count()
    assert result["count"] == 0, result
    assert remaining == 2, result
    assert cells == 0


def test_residual_does_not_place_without_classroom() -> None:
    ids = _seed_shift2_math_teacher(n_classes=1, hours=2, with_classroom=False)
    with SessionLocal() as session:
        from app.services.auto_scheduler import AutoScheduler

        result = None
        for event in AutoScheduler(session, school_id=TEST_SCHOOL_ID).repair_iter(
            school_level="secondary"
        ):
            if event.get("type") == "done":
                result = event
        cells = session.query(ScheduleCell).count()
    assert result is not None
    assert result.get("count") == 0, result
    assert cells == 0


def test_workload_shows_class_hours_not_sum_of_subgroups() -> None:
    with SessionLocal() as session:
        subject = Subject(school_id=TEST_SCHOOL_ID, name="Информатика")
        t1 = Teacher(school_id=TEST_SCHOOL_ID, full_name="Отепбергенов М.М.")
        t2 = Teacher(school_id=TEST_SCHOOL_ID, full_name="Иванов И.И.")
        cls = SchoolClass(
            school_id=TEST_SCHOOL_ID, name="5А", grade=5, school_level="secondary"
        )
        session.add_all([subject, t1, t2, cls])
        session.flush()
        session.add_all(
            [
                TeachingAssignment(
                    school_id=TEST_SCHOOL_ID,
                    subject_id=subject.id,
                    class_id=cls.id,
                    teacher_id=t1.id,
                    hours_per_week=2,
                    group_number=1,
                ),
                TeachingAssignment(
                    school_id=TEST_SCHOOL_ID,
                    subject_id=subject.id,
                    class_id=cls.id,
                    teacher_id=t2.id,
                    hours_per_week=2,
                    group_number=2,
                ),
            ]
        )
        session.commit()
        subject_id, class_id = subject.id, cls.id

    listed = client.get("/api/workload/?school_level=secondary")
    assert listed.status_code == 200, listed.text
    cells = [
        c
        for c in listed.json()["cells"]
        if c["class_id"] == class_id and c["subject_id"] == subject_id
    ]
    assert cells == [{"class_id": class_id, "subject_id": subject_id, "hours": 2}]

    upd = client.put(
        "/api/workload/cell",
        json={"class_id": class_id, "subject_id": subject_id, "hours": 3},
    )
    assert upd.status_code == 200, upd.text

    with SessionLocal() as session:
        rows = list(
            session.scalars(
                select(TeachingAssignment).where(
                    TeachingAssignment.class_id == class_id,
                    TeachingAssignment.subject_id == subject_id,
                )
            ).all()
        )
        assert len(rows) == 2
        assert {r.hours_per_week for r in rows} == {3}

    refreshed = client.get("/api/workload/?school_level=secondary")
    cells = [
        c
        for c in refreshed.json()["cells"]
        if c["class_id"] == class_id and c["subject_id"] == subject_id
    ]
    assert cells == [{"class_id": class_id, "subject_id": subject_id, "hours": 3}]


def test_fixed_subject_rejects_wrong_classroom() -> None:
    with SessionLocal() as session:
        shift = Shift(
            school_id=TEST_SCHOOL_ID,
            name="1 смена",
            school_level="secondary",
            start_lesson=1,
            lessons_count=5,
            working_days=5,
            max_lessons_per_day=5,
        )
        info = Subject(
            school_id=TEST_SCHOOL_ID,
            name="Информатика",
            requires_fixed_classroom=True,
        )
        math = Subject(school_id=TEST_SCHOOL_ID, name="Математика")
        teacher = Teacher(school_id=TEST_SCHOOL_ID, full_name="Баер Э.В.")
        cls = SchoolClass(
            school_id=TEST_SCHOOL_ID, name="7А", grade=7, school_level="secondary"
        )
        session.add_all([shift, info, math, teacher, cls])
        session.flush()
        cls.shift_id = shift.id
        lab = Classroom(
            school_id=TEST_SCHOOL_ID,
            number="32",
            is_exclusive=True,
        )
        math_room = Classroom(
            school_id=TEST_SCHOOL_ID,
            number="43",
            is_exclusive=False,
        )
        session.add_all([lab, math_room])
        session.flush()
        lab.subjects = [info]
        math_room.subjects = [math]
        assignment = TeachingAssignment(
            school_id=TEST_SCHOOL_ID,
            subject_id=info.id,
            teacher_id=teacher.id,
            class_id=cls.id,
            hours_per_week=2,
        )
        session.add(assignment)
        session.commit()
        class_id = cls.id
        assignment_id = assignment.id
        math_room_id = math_room.id
        lab_id = lab.id

    denied = client.post(
        "/api/schedule/cells",
        json={
            "class_id": class_id,
            "day_of_week": 1,
            "lesson_number": 1,
            "assignment_id": assignment_id,
            "classroom_id": math_room_id,
        },
    )
    assert denied.status_code == 422, denied.text

    ok = client.post(
        "/api/schedule/cells",
        json={
            "class_id": class_id,
            "day_of_week": 1,
            "lesson_number": 1,
            "assignment_id": assignment_id,
            "classroom_id": lab_id,
        },
    )
    assert ok.status_code == 201, ok.text


def test_elementary_classroom_blocks_secondary() -> None:
    with SessionLocal() as session:
        shift = Shift(
            school_id=TEST_SCHOOL_ID,
            name="1 смена",
            school_level="secondary",
            start_lesson=1,
            lessons_count=5,
            working_days=5,
            max_lessons_per_day=5,
        )
        math = Subject(school_id=TEST_SCHOOL_ID, name="Математика")
        teacher = Teacher(school_id=TEST_SCHOOL_ID, full_name="Баер Э.В.")
        cls = SchoolClass(
            school_id=TEST_SCHOOL_ID, name="7А", grade=7, school_level="secondary"
        )
        session.add_all([shift, math, teacher, cls])
        session.flush()
        cls.shift_id = shift.id
        elem_room = Classroom(
            school_id=TEST_SCHOOL_ID,
            number="11",
            school_level="elementary",
        )
        gym = Classroom(school_id=TEST_SCHOOL_ID, number="СЗ")
        session.add_all([elem_room, gym])
        session.flush()
        assignment = TeachingAssignment(
            school_id=TEST_SCHOOL_ID,
            subject_id=math.id,
            teacher_id=teacher.id,
            class_id=cls.id,
            hours_per_week=2,
        )
        session.add(assignment)
        session.commit()
        class_id = cls.id
        assignment_id = assignment.id
        elem_id = elem_room.id
        gym_id = gym.id

    denied = client.post(
        "/api/schedule/cells",
        json={
            "class_id": class_id,
            "day_of_week": 1,
            "lesson_number": 1,
            "assignment_id": assignment_id,
            "classroom_id": elem_id,
        },
    )
    assert denied.status_code == 422, denied.text
    errors = denied.json()["detail"]["errors"]
    assert any("начальной" in e for e in errors)

    ok = client.post(
        "/api/schedule/cells",
        json={
            "class_id": class_id,
            "day_of_week": 1,
            "lesson_number": 1,
            "assignment_id": assignment_id,
            "classroom_id": gym_id,
        },
    )
    assert ok.status_code == 201, ok.text


def test_assist_phrase_saves_early_pref() -> None:
    r = client.post(
        "/api/schedule/assist",
        json={
            "message": "физику не после пятого",
            "school_level": "secondary",
            "apply": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["preference_updates"]["pref_hard_subjects_early"] == 10
    assert body["preferences_applied"] is True
    assert body["llm_used"] is False
    settings = client.get("/api/schedule/settings").json()
    assert settings["secondary"]["pref_hard_subjects_early"] == 10


def test_assist_moves_late_physics_to_early_slot() -> None:
    with SessionLocal() as session:
        shift = Shift(
            school_id=TEST_SCHOOL_ID,
            name="1 смена",
            school_level="secondary",
            start_lesson=1,
            lessons_count=6,
            working_days=5,
            max_lessons_per_day=7,
        )
        phys = Subject(school_id=TEST_SCHOOL_ID, name="Физика")
        teacher = Teacher(school_id=TEST_SCHOOL_ID, full_name="Петров П.П.")
        session.add_all([shift, phys, teacher])
        session.flush()
        cls = SchoolClass(
            school_id=TEST_SCHOOL_ID,
            name="7А",
            grade=7,
            school_level="secondary",
            shift_id=shift.id,
        )
        session.add(cls)
        session.flush()
        asg = TeachingAssignment(
            school_id=TEST_SCHOOL_ID,
            subject_id=phys.id,
            teacher_id=teacher.id,
            class_id=cls.id,
            hours_per_week=2,
        )
        session.add(asg)
        session.flush()
        session.add(
            ScheduleCell(
                school_id=TEST_SCHOOL_ID,
                class_id=cls.id,
                day_of_week=1,
                lesson_number=6,
                assignment_id=asg.id,
            )
        )
        session.commit()
        cell_id = session.query(ScheduleCell).one().id

    preview = client.post(
        "/api/schedule/assist",
        json={
            "message": "физику не после пятого",
            "school_level": "secondary",
            "apply": False,
        },
    )
    assert preview.status_code == 200, preview.text
    plan = preview.json()
    assert plan["moves"], plan
    assert plan["moves"][0]["from_lesson"] == 6
    assert plan["moves"][0]["to_lesson"] <= 5
    assert plan["applied_moves"] == 0

    applied = client.post(
        "/api/schedule/assist",
        json={
            "message": "физику не после пятого",
            "school_level": "secondary",
            "apply": True,
        },
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["applied_moves"] == 1
    with SessionLocal() as session:
        cell = session.get(ScheduleCell, cell_id)
        assert cell is not None
        assert cell.lesson_number <= 5

