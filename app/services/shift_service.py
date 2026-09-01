"""Shift catalog CRUD and bell schedule updates."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domain import fmt_time, lesson_end_exclusive
from app.models import Shift, ShiftLessonTime
from app.services.tenancy import require_owned


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


def _clamp_class_hour_lessons(
    count: int | None, lessons_count: int, class_hour_day: int | None
) -> int | None:
    if not class_hour_day or count is None:
        return None
    return max(1, min(int(count), int(lessons_count)))


def serialize_shift(db: Session, shift: Shift) -> dict[str, Any]:
    """Materialise lesson_times for Pydantic response_model."""
    lesson_times = list(
        db.scalars(
            select(ShiftLessonTime)
            .where(ShiftLessonTime.shift_id == shift.id)
            .order_by(ShiftLessonTime.day_of_week, ShiftLessonTime.lesson_number)
        ).all()
    )
    return {
        "id": shift.id,
        "name": shift.name,
        "school_level": shift.school_level,
        "school_level_display": shift.school_level_display,
        "start_lesson": shift.start_lesson,
        "lessons_count": shift.lessons_count,
        "working_days": shift.working_days,
        "max_lessons_per_day": shift.max_lessons_per_day,
        "class_hour_day": shift.class_hour_day,
        "class_hour_start": fmt_time(shift.class_hour_start),
        "class_hour_end": fmt_time(shift.class_hour_end),
        "class_hour_lessons_count": shift.class_hour_lessons_count,
        "lesson_times": [
            {
                "id": lt.id,
                "day_of_week": lt.day_of_week,
                "lesson_number": lt.lesson_number,
                "time_start": fmt_time(lt.time_start) or "",
                "time_end": fmt_time(lt.time_end) or "",
            }
            for lt in lesson_times
        ],
    }


def _parse_pair(
    label: str, lesson: int, s: str, e: str
) -> tuple[tuple[time, time] | None, list[str]]:
    s = (s or "").strip()
    e = (e or "").strip()
    if not s and not e:
        return None, []
    if not s or not e:
        return None, [
            f"{label}, урок {lesson}: укажите оба времени или оставьте пустым"
        ]
    try:
        ts = datetime.strptime(s, "%H:%M").time()
        te = datetime.strptime(e, "%H:%M").time()
    except ValueError:
        return None, [f"{label}, урок {lesson}: неверный формат времени"]
    if ts >= te:
        return None, [f"{label}, урок {lesson}: конец позже начала"]
    return (ts, te), []


@dataclass
class BellScheduleAppliedData:
    inserted: int
    warnings: list[str] = field(default_factory=list)


@dataclass
class BellTimePairData:
    time_start: str = ""
    time_end: str = ""


class ShiftService:
    def __init__(self, db: Session, school_id: int):
        self.db = db
        self.school_id = school_id

    def list(self) -> list[dict[str, Any]]:
        rows = list(
            self.db.scalars(
                select(Shift)
                .where(Shift.school_id == self.school_id)
                .order_by(Shift.school_level, Shift.name)
            ).all()
        )
        return [serialize_shift(self.db, s) for s in rows]

    def get(self, shift_id: int) -> dict[str, Any]:
        row = require_owned(self.db, Shift, shift_id, self.school_id)
        return serialize_shift(self.db, row)

    def create(
        self,
        *,
        name: str,
        school_level: str,
        start_lesson: int = 1,
        lessons_count: int = 6,
        working_days: int = 5,
        max_lessons_per_day: int = 7,
        class_hour_day: int | None = None,
        class_hour_start: str | None = None,
        class_hour_end: str | None = None,
        class_hour_lessons_count: int | None = None,
    ) -> dict[str, Any]:
        start, count = _clamp_shift_bounds(
            start_lesson, lessons_count, max_lessons_per_day
        )
        shift = Shift(
            school_id=self.school_id,
            name=name.strip(),
            school_level=school_level,
            start_lesson=start,
            lessons_count=count,
            working_days=working_days,
            max_lessons_per_day=max_lessons_per_day,
        )
        wd = working_days
        if class_hour_day and class_hour_day <= wd:
            shift.class_hour_day = class_hour_day
            ts = _parse_hm(class_hour_start)
            te = _parse_hm(class_hour_end)
            if ts and te and ts < te:
                shift.class_hour_start = ts
                shift.class_hour_end = te
            shift.class_hour_lessons_count = _clamp_class_hour_lessons(
                class_hour_lessons_count, count, class_hour_day
            )
        self.db.add(shift)
        self.db.commit()
        self.db.refresh(shift)
        return self.get(shift.id)

    def update(
        self,
        shift_id: int,
        *,
        name: str | None = None,
        school_level: str | None = None,
        start_lesson: int | None = None,
        lessons_count: int | None = None,
        working_days: int | None = None,
        max_lessons_per_day: int | None = None,
        class_hour_day: int | None = None,
        class_hour_start: str | None = None,
        class_hour_end: str | None = None,
        class_hour_lessons_count: int | None = None,
        fields_set: frozenset[str] | None = None,
    ) -> dict[str, Any]:
        shift = require_owned(self.db, Shift, shift_id, self.school_id)
        if fields_set is None:
            fields_set = frozenset()
        if "name" in fields_set and name is not None:
            shift.name = str(name).strip()
        if "school_level" in fields_set and school_level is not None:
            shift.school_level = school_level
        max_cap = (
            max_lessons_per_day
            if "max_lessons_per_day" in fields_set and max_lessons_per_day is not None
            else shift.max_lessons_per_day
        )
        if max_cap is None:
            max_cap = shift.max_lessons_per_day
        start = start_lesson if "start_lesson" in fields_set else shift.start_lesson
        count = lessons_count if "lessons_count" in fields_set else shift.lessons_count
        if (
            "start_lesson" in fields_set
            or "lessons_count" in fields_set
            or "max_lessons_per_day" in fields_set
        ):
            start = start if start is not None else shift.start_lesson
            count = count if count is not None else shift.lessons_count
            start, count = _clamp_shift_bounds(int(start), int(count), int(max_cap))
            shift.start_lesson = start
            shift.lessons_count = count
        if "working_days" in fields_set and working_days is not None:
            shift.working_days = int(working_days)
        if "max_lessons_per_day" in fields_set and max_lessons_per_day is not None:
            shift.max_lessons_per_day = int(max_lessons_per_day)
        if "class_hour_day" in fields_set:
            shift.class_hour_day = class_hour_day
        if "class_hour_start" in fields_set:
            shift.class_hour_start = _parse_hm(class_hour_start)
        if "class_hour_end" in fields_set:
            shift.class_hour_end = _parse_hm(class_hour_end)
        wd = shift.working_days or 5
        if shift.class_hour_day and shift.class_hour_day > wd:
            shift.class_hour_day = None
            shift.class_hour_start = None
            shift.class_hour_end = None
            shift.class_hour_lessons_count = None
        if shift.class_hour_day:
            raw_count = (
                class_hour_lessons_count
                if "class_hour_lessons_count" in fields_set
                else shift.class_hour_lessons_count
            )
            shift.class_hour_lessons_count = _clamp_class_hour_lessons(
                raw_count, shift.lessons_count, shift.class_hour_day
            )
        else:
            shift.class_hour_lessons_count = None
        self.db.commit()
        self.db.refresh(shift)
        return self.get(shift.id)

    def delete(self, shift_id: int) -> None:
        shift = require_owned(self.db, Shift, shift_id, self.school_id)
        self.db.delete(shift)
        self.db.commit()

    def update_lesson_times(
        self,
        shift_id: int,
        *,
        common: dict[str, BellTimePairData],
        class_day: dict[str, BellTimePairData],
    ) -> BellScheduleAppliedData:
        shift = require_owned(self.db, Shift, shift_id, self.school_id)

        start = shift.start_lesson
        wd = shift.working_days or 5
        class_day_num = (
            shift.class_hour_day
            if shift.class_hour_day and shift.class_hour_day <= wd
            else None
        )

        warnings: list[str] = []
        common_by_lesson: dict[int, tuple[time, time] | None] = {}
        class_day_by_lesson: dict[int, tuple[time, time] | None] = {}

        for n in range(start, start + shift.lessons_count):
            key = str(n)
            common_pair = common.get(key)
            class_pair = class_day.get(key)
            cpair, cwarns = _parse_pair(
                "Остальные дни",
                n,
                common_pair.time_start if common_pair else "",
                common_pair.time_end if common_pair else "",
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

        self.db.execute(
            delete(ShiftLessonTime).where(ShiftLessonTime.shift_id == shift.id)
        )

        inserted = 0
        for day in range(1, min(wd, 6) + 1):
            day_end = lesson_end_exclusive(shift, day)
            for n in range(start, day_end):
                pair = (
                    class_day_by_lesson.get(n)
                    if class_day_num and day == class_day_num
                    else common_by_lesson.get(n)
                )
                if not pair:
                    continue
                ts, te = pair
                self.db.add(
                    ShiftLessonTime(
                        school_id=self.school_id,
                        shift_id=shift.id,
                        day_of_week=day,
                        lesson_number=n,
                        time_start=ts,
                        time_end=te,
                    )
                )
                inserted += 1
        self.db.commit()
        return BellScheduleAppliedData(inserted=inserted, warnings=warnings)
