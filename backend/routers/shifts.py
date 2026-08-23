"""Shifts CRUD API (scalar fields; lesson_times preserved / empty on create)."""
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.models import School
from app.services.errors import ServiceError
from app.services.shift_service import BellTimePairData, ShiftService
from backend.deps import get_current_school, get_db
from backend.http_errors import raise_http
from backend.schemas.shifts import (
    BellScheduleApplied,
    BellScheduleUpdate,
    ShiftCreate,
    ShiftOut,
    ShiftUpdate,
)

router = APIRouter()


@router.get("/", response_model=list[ShiftOut])
def list_shifts(
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> list[dict[str, Any]]:
    try:
        return ShiftService(db, school.id).list()
    except ServiceError as exc:
        raise_http(exc)


@router.get("/{shift_id}", response_model=ShiftOut)
def get_shift(
    shift_id: int,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> dict[str, Any]:
    try:
        return ShiftService(db, school.id).get(shift_id)
    except ServiceError as exc:
        raise_http(exc)


@router.post("/", response_model=ShiftOut)
def create_shift(
    body: ShiftCreate,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> dict[str, Any]:
    try:
        return ShiftService(db, school.id).create(
            name=body.name,
            school_level=body.school_level,
            start_lesson=body.start_lesson,
            lessons_count=body.lessons_count,
            working_days=body.working_days,
            max_lessons_per_day=body.max_lessons_per_day,
            class_hour_day=body.class_hour_day,
            class_hour_start=body.class_hour_start,
            class_hour_end=body.class_hour_end,
        )
    except ServiceError as exc:
        raise_http(exc)


@router.put("/{shift_id}", response_model=ShiftOut)
def update_shift(
    shift_id: int,
    body: ShiftUpdate,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> dict[str, Any]:
    data = body.model_dump(exclude_unset=True)
    try:
        return ShiftService(db, school.id).update(
            shift_id,
            name=data.get("name"),
            school_level=data.get("school_level"),
            start_lesson=data.get("start_lesson"),
            lessons_count=data.get("lessons_count"),
            working_days=data.get("working_days"),
            max_lessons_per_day=data.get("max_lessons_per_day"),
            class_hour_day=data.get("class_hour_day"),
            class_hour_start=data.get("class_hour_start"),
            class_hour_end=data.get("class_hour_end"),
            fields_set=frozenset(data.keys()),
        )
    except ServiceError as exc:
        raise_http(exc)


@router.delete("/{shift_id}", status_code=204)
def delete_shift(
    shift_id: int,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> None:
    try:
        ShiftService(db, school.id).delete(shift_id)
    except ServiceError as exc:
        raise_http(exc)


@router.put("/{shift_id}/lesson-times", response_model=BellScheduleApplied)
def update_lesson_times(
    shift_id: int,
    body: BellScheduleUpdate,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> BellScheduleApplied:
    """Replace the bell schedule for a shift.

    `common` applies to every working day except the class-hour day;
    `class_day` applies to the class-hour day only (if set).
    """
    common = {
        k: BellTimePairData(time_start=v.time_start, time_end=v.time_end)
        for k, v in body.common.items()
    }
    class_day = {
        k: BellTimePairData(time_start=v.time_start, time_end=v.time_end)
        for k, v in body.class_day.items()
    }
    try:
        result = ShiftService(db, school.id).update_lesson_times(
            shift_id, common=common, class_day=class_day
        )
    except ServiceError as exc:
        raise_http(exc)
    return BellScheduleApplied(inserted=result.inserted, warnings=result.warnings)
