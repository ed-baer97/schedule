"""Schedule grid API (CRUD over schedule cells, plus grid metadata)."""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.models import School, User
from app.services.job_service import JobService
from app.services.schedule_service import ScheduleService
from backend.deps import get_current_school, get_current_user, get_db
from backend.schemas.schedule import (
    AssignmentChoiceOut,
    AssignmentsForClassOut,
    AutoAllStreamBody,
    AutoByTeacherStreamBody,
    AutoPageData,
    ClassroomChoiceOut,
    ClassroomWarningOut,
    ClearScheduleBody,
    ClearScheduleResult,
    ScheduleCellCreate,
    ScheduleCellMove,
    ScheduleCellOut,
    ScheduleGridOut,
    ScheduleSettingsOut,
    SchoolClassRow,
    SettingsPair,
    SettingsUpdate,
    ShiftBrief,
    TeacherBrief,
)

router = APIRouter()


@router.get("/grid", response_model=ScheduleGridOut)
def get_grid(
    school_level: str = Query("elementary", pattern="^(elementary|secondary)$"),
    shift_id: int | None = Query(None),
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> ScheduleGridOut:
    data = ScheduleService(db, school.id).get_grid(school_level, shift_id)
    return ScheduleGridOut(
        school_level=data.school_level,
        current_shift_id=data.current_shift_id,
        current_shift=(
            ShiftBrief.model_validate(asdict(data.current_shift))
            if data.current_shift
            else None
        ),
        shifts=[ShiftBrief.model_validate(asdict(s)) for s in data.shifts],
        classes=[SchoolClassRow.model_validate(asdict(c)) for c in data.classes],
        day_names=data.day_names,
        working_days=data.working_days,
        max_lessons=data.max_lessons,
        lessons_range=data.lessons_range,
        lesson_times_by_day=data.lesson_times_by_day,
        class_hour_time_label=data.class_hour_time_label,
        cells=[ScheduleCellOut(**c) for c in data.cells],
        classroom_warnings=[
            ClassroomWarningOut.model_validate(asdict(w))
            for w in data.classroom_warnings
        ],
        settings=(
            ScheduleSettingsOut.model_validate(asdict(data.settings))
            if data.settings
            else None
        ),
    )


@router.get(
    "/assignments-for-class/{class_id}",
    response_model=AssignmentsForClassOut,
)
def assignments_for_class(
    class_id: int,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> AssignmentsForClassOut:
    data = ScheduleService(db, school.id).assignments_for_class(class_id)
    return AssignmentsForClassOut(
        assignments=[
            AssignmentChoiceOut.model_validate(asdict(a)) for a in data.assignments
        ],
        classrooms=[
            ClassroomChoiceOut.model_validate(asdict(r)) for r in data.classrooms
        ],
    )


@router.post("/cells", response_model=ScheduleCellOut, status_code=201)
def create_cell(
    body: ScheduleCellCreate,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> ScheduleCellOut:
    cell = ScheduleService(db, school.id).create_cell(
        class_id=body.class_id,
        day_of_week=body.day_of_week,
        lesson_number=body.lesson_number,
        assignment_id=body.assignment_id,
        classroom_id=body.classroom_id,
    )
    return ScheduleCellOut(**cell)


@router.patch("/cells/{cell_id}", response_model=ScheduleCellOut)
def move_cell(
    cell_id: int,
    body: ScheduleCellMove,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> ScheduleCellOut:
    cell = ScheduleService(db, school.id).move_cell(
        cell_id,
        day_of_week=body.day_of_week,
        lesson_number=body.lesson_number,
        class_id=body.class_id,
        classroom_id=body.classroom_id,
        set_classroom=body.set_classroom,
    )
    return ScheduleCellOut(**cell)


@router.delete("/cells/{cell_id}", status_code=204, response_class=Response)
def delete_cell(
    cell_id: int,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> Response:
    ScheduleService(db, school.id).delete_cell(cell_id)
    return Response(status_code=204)


@router.get("/auto/page-data", response_model=AutoPageData)
def auto_page_data(
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> AutoPageData:
    data = ScheduleService(db, school.id).auto_page_data()
    return AutoPageData(
        teachers=[TeacherBrief.model_validate(asdict(t)) for t in data.teachers],
        classes=[SchoolClassRow.model_validate(asdict(c)) for c in data.classes],
        elementary_warnings=[
            ClassroomWarningOut.model_validate(asdict(w))
            for w in data.elementary_warnings
        ],
        secondary_warnings=[
            ClassroomWarningOut.model_validate(asdict(w))
            for w in data.secondary_warnings
        ],
        elementary_settings=(
            ScheduleSettingsOut.model_validate(asdict(data.elementary_settings))
            if data.elementary_settings
            else None
        ),
        secondary_settings=(
            ScheduleSettingsOut.model_validate(asdict(data.secondary_settings))
            if data.secondary_settings
            else None
        ),
        shifts_elementary=[
            ShiftBrief.model_validate(asdict(s)) for s in data.shifts_elementary
        ],
        shifts_secondary=[
            ShiftBrief.model_validate(asdict(s)) for s in data.shifts_secondary
        ],
    )


@router.post("/auto", status_code=202)
def enqueue_auto_all(
    body: AutoAllStreamBody,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
    user: User = Depends(get_current_user),
) -> dict:
    return JobService(db, school.id).enqueue_auto(
        kind="auto_all",
        payload=body.model_dump(),
        created_by_id=user.id,
    )


@router.post("/auto/by-teacher", status_code=202)
def enqueue_auto_by_teacher(
    body: AutoByTeacherStreamBody,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
    user: User = Depends(get_current_user),
) -> dict:
    return JobService(db, school.id).enqueue_auto(
        kind="auto_by_teacher",
        payload=body.model_dump(),
        created_by_id=user.id,
    )


@router.post("/clear", response_model=ClearScheduleResult)
def clear_schedule(
    body: ClearScheduleBody,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> ClearScheduleResult:
    count = ScheduleService(db, school.id).clear_schedule(
        school_level=body.school_level,
        class_id=body.class_id,
        teacher_id=body.teacher_id,
    )
    return ClearScheduleResult(count=count)


@router.get("/settings", response_model=SettingsPair)
def get_settings(
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> SettingsPair:
    data = ScheduleService(db, school.id).get_settings()
    return SettingsPair(
        elementary=(
            ScheduleSettingsOut.model_validate(asdict(data.elementary))
            if data.elementary
            else None
        ),
        secondary=(
            ScheduleSettingsOut.model_validate(asdict(data.secondary))
            if data.secondary
            else None
        ),
    )


@router.put("/settings/{school_level}", response_model=ScheduleSettingsOut)
def update_settings(
    school_level: str,
    body: SettingsUpdate,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> ScheduleSettingsOut:
    s = ScheduleService(db, school.id).update_settings(
        school_level,
        max_lessons_per_subject_per_day=body.max_lessons_per_subject_per_day,
        classroom_mode=body.classroom_mode,
        elementary_group_subjects_leave=body.elementary_group_subjects_leave,
    )
    return ScheduleSettingsOut.model_validate(asdict(s))
