"""Shifts CRUD API (scalar fields; lesson_times preserved / empty on create)."""
from datetime import datetime, time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Shift, ShiftLessonTime

from backend.deps import get_db
from backend.schemas.shifts import (
    BellScheduleApplied,
    BellScheduleUpdate,
    ShiftCreate,
    ShiftOut,
    ShiftUpdate,
)

router = APIRouter()


def _parse_hm(s: str | None) -> time | None:
    if not s or not str(s).strip():
        return None
    return datetime.strptime(str(s).strip(), "%H:%M").time()


def _clamp_shift_bounds(
    start_lesson: int, lessons_count: int, max_lessons_cap: int
) -> tuple[int, int]:
    max_cap = max(1, min(int(max_lessons_cap), 10))
    start_lesson = max(1, min(int(start_lesson), max_cap))
    max_count = max(1, max_cap - start_lesson + 1)
    lessons_count = max(1, min(int(lessons_count), max_count))
    return start_lesson, lessons_count


def _serialize_shift(db: Session, shift: Shift) -> dict[str, Any]:
    """Materialise the dynamic lesson_times relationship for Pydantic."""
    lesson_times = list(
        db.scalars(
            select(ShiftLessonTime)
            .where(ShiftLessonTime.shift_id == shift.id)
            .order_by(ShiftLessonTime.day_of_week, ShiftLessonTime.lesson_number)
        ).all()
    )
    data = ShiftOut.model_validate(shift, from_attributes=True).model_dump()
    data["lesson_times"] = [
        {
            "id": lt.id,
            "day_of_week": lt.day_of_week,
            "lesson_number": lt.lesson_number,
            "time_start": lt.time_start.strftime("%H:%M") if lt.time_start else "",
            "time_end": lt.time_end.strftime("%H:%M") if lt.time_end else "",
        }
        for lt in lesson_times
    ]
    return data


@router.get("/", response_model=list[ShiftOut])
def list_shifts(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = list(
        db.scalars(select(Shift).order_by(Shift.school_level, Shift.name)).all()
    )
    return [_serialize_shift(db, s) for s in rows]


@router.get("/{shift_id}", response_model=ShiftOut)
def get_shift(shift_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    row = db.get(Shift, shift_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Shift not found")
    return _serialize_shift(db, row)


@router.post("/", response_model=ShiftOut)
def create_shift(body: ShiftCreate, db: Session = Depends(get_db)) -> Shift:
    start, count = _clamp_shift_bounds(
        body.start_lesson, body.lessons_count, body.max_lessons_per_day
    )
    shift = Shift(
        name=body.name.strip(),
        school_level=body.school_level,
        start_lesson=start,
        lessons_count=count,
        working_days=body.working_days,
        max_lessons_per_day=body.max_lessons_per_day,
    )
    wd = body.working_days
    if body.class_hour_day and body.class_hour_day <= wd:
        shift.class_hour_day = body.class_hour_day
        ts = _parse_hm(body.class_hour_start)
        te = _parse_hm(body.class_hour_end)
        if ts and te and ts < te:
            shift.class_hour_start = ts
            shift.class_hour_end = te
    db.add(shift)
    db.commit()
    db.refresh(shift)
    return get_shift(shift.id, db)


@router.put("/{shift_id}", response_model=ShiftOut)
def update_shift(
    shift_id: int, body: ShiftUpdate, db: Session = Depends(get_db)
) -> Shift:
    shift = db.get(Shift, shift_id)
    if shift is None:
        raise HTTPException(status_code=404, detail="Shift not found")
    data = body.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        shift.name = str(data["name"]).strip()
    if "school_level" in data and data["school_level"] is not None:
        shift.school_level = data["school_level"]
    max_cap = data.get("max_lessons_per_day", shift.max_lessons_per_day)
    if max_cap is None:
        max_cap = shift.max_lessons_per_day
    start = data.get("start_lesson", shift.start_lesson)
    count = data.get("lessons_count", shift.lessons_count)
    if start is not None or count is not None or "max_lessons_per_day" in data:
        start = start if start is not None else shift.start_lesson
        count = count if count is not None else shift.lessons_count
        start, count = _clamp_shift_bounds(int(start), int(count), int(max_cap))
        shift.start_lesson = start
        shift.lessons_count = count
    if "working_days" in data and data["working_days"] is not None:
        shift.working_days = int(data["working_days"])
    if "max_lessons_per_day" in data and data["max_lessons_per_day"] is not None:
        shift.max_lessons_per_day = int(data["max_lessons_per_day"])
    if "class_hour_day" in data:
        shift.class_hour_day = data["class_hour_day"]
    if "class_hour_start" in data:
        shift.class_hour_start = _parse_hm(data.get("class_hour_start"))
    if "class_hour_end" in data:
        shift.class_hour_end = _parse_hm(data.get("class_hour_end"))
    wd = shift.working_days or 5
    if shift.class_hour_day and shift.class_hour_day > wd:
        shift.class_hour_day = None
        shift.class_hour_start = None
        shift.class_hour_end = None
    db.commit()
    db.refresh(shift)
    return get_shift(shift.id, db)


@router.delete("/{shift_id}", status_code=204)
def delete_shift(shift_id: int, db: Session = Depends(get_db)) -> None:
    shift = db.get(Shift, shift_id)
    if shift is None:
        raise HTTPException(status_code=404, detail="Shift not found")
    db.delete(shift)
    db.commit()


def _parse_pair(label: str, lesson: int, s: str, e: str) -> tuple[time, time] | tuple[None, list[str]]:
    s = (s or "").strip()
    e = (e or "").strip()
    if not s and not e:
        return None, []
    if not s or not e:
        return None, [f"{label}, урок {lesson}: укажите оба времени или оставьте пустым"]
    try:
        ts = datetime.strptime(s, "%H:%M").time()
        te = datetime.strptime(e, "%H:%M").time()
    except ValueError:
        return None, [f"{label}, урок {lesson}: неверный формат времени"]
    if ts >= te:
        return None, [f"{label}, урок {lesson}: конец позже начала"]
    return (ts, te), []


@router.put("/{shift_id}/lesson-times", response_model=BellScheduleApplied)
def update_lesson_times(
    shift_id: int,
    body: BellScheduleUpdate,
    db: Session = Depends(get_db),
) -> BellScheduleApplied:
    """Replace the bell schedule for a shift.

    `common` applies to every working day except the class-hour day;
    `class_day` applies to the class-hour day only (if set).
    """
    shift = db.get(Shift, shift_id)
    if shift is None:
        raise HTTPException(status_code=404, detail="Shift not found")

    start = shift.start_lesson
    wd = shift.working_days or 5
    class_day = (
        shift.class_hour_day
        if shift.class_hour_day and shift.class_hour_day <= wd
        else None
    )

    warnings: list[str] = []
    common_by_lesson: dict[int, tuple[time, time] | None] = {}
    class_day_by_lesson: dict[int, tuple[time, time] | None] = {}

    for n in range(start, start + shift.lessons_count):
        key = str(n)
        common = body.common.get(key)
        class_pair = body.class_day.get(key)
        cpair, cwarns = _parse_pair(
            "Остальные дни",
            n,
            common.time_start if common else "",
            common.time_end if common else "",
        )
        warnings.extend(cwarns)
        common_by_lesson[n] = cpair
        kpair, kwarns = _parse_pair(
            "День классного часа",
            n,
            class_pair.time_start if class_pair else "",
            class_pair.time_end if class_pair else "",
        )
        warnings.extend(kwarns)
        class_day_by_lesson[n] = kpair

    db.execute(delete(ShiftLessonTime).where(ShiftLessonTime.shift_id == shift.id))

    inserted = 0
    for day in range(1, min(wd, 6) + 1):
        for n in range(start, start + shift.lessons_count):
            pair = (
                class_day_by_lesson.get(n)
                if class_day and day == class_day
                else common_by_lesson.get(n)
            )
            if not pair:
                continue
            ts, te = pair
            db.add(
                ShiftLessonTime(
                    shift_id=shift.id,
                    day_of_week=day,
                    lesson_number=n,
                    time_start=ts,
                    time_end=te,
                )
            )
            inserted += 1
    db.commit()
    return BellScheduleApplied(inserted=inserted, warnings=warnings)
