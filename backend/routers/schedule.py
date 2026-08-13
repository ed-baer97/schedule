"""Schedule grid API (CRUD over schedule cells, plus grid metadata)."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    Classroom,
    ScheduleCell,
    ScheduleSettings,
    SchoolClass,
    Shift,
    Teacher,
    TeachingAssignment,
)
from app.services.auto_scheduler import AutoScheduler
from app.services.validators import ScheduleValidator

from backend.deps import SessionLocal, get_db
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

_DAY_NAMES = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"]

_CELL_LOAD = (
    joinedload(ScheduleCell.assignment).joinedload(TeachingAssignment.subject),
    joinedload(ScheduleCell.assignment).joinedload(TeachingAssignment.teacher),
    joinedload(ScheduleCell.classroom),
)


def _fmt_time(t) -> str | None:
    if t is None:
        return None
    return t.strftime("%H:%M") if hasattr(t, "strftime") else str(t)


def _shift_to_brief(s: Shift) -> ShiftBrief:
    label: str | None = None
    if s.class_hour_start and s.class_hour_end:
        label = f"{_fmt_time(s.class_hour_start)}–{_fmt_time(s.class_hour_end)}"
    return ShiftBrief(
        id=s.id,
        name=s.name,
        school_level=s.school_level,
        working_days=s.working_days,
        max_lessons_per_day=s.max_lessons_per_day,
        start_lesson=s.start_lesson,
        lessons_count=s.lessons_count,
        class_hour_day=s.class_hour_day,
        class_hour_time_label=label,
    )


def _cell_to_out(cell: ScheduleCell) -> ScheduleCellOut:
    a = cell.assignment
    subj = a.subject if a else None
    teacher = a.teacher if a else None
    return ScheduleCellOut(
        id=cell.id,
        class_id=cell.class_id,
        day_of_week=cell.day_of_week,
        lesson_number=cell.lesson_number,
        assignment_id=cell.assignment_id,
        classroom_id=cell.classroom_id,
        subject_id=subj.id if subj else 0,
        subject_name=subj.display_name if subj else "?",
        subject_color=(subj.display_color if subj else "#3498db"),
        teacher_id=teacher.id if teacher else None,
        teacher_name=teacher.display_name if teacher else None,
        group_number=a.group_number if a else None,
        classroom_name=cell.classroom.display_name if cell.classroom else None,
    )


def _reload_cell(db: Session, cell_id: int) -> ScheduleCell:
    cell = (
        db.execute(
            select(ScheduleCell).options(*_CELL_LOAD).where(ScheduleCell.id == cell_id)
        )
        .scalars()
        .unique()
        .one()
    )
    return cell


@router.get("/grid", response_model=ScheduleGridOut)
def get_grid(
    school_level: str = Query("elementary", pattern="^(elementary|secondary)$"),
    shift_id: int | None = Query(None),
    db: Session = Depends(get_db),
) -> ScheduleGridOut:
    shifts = list(
        db.scalars(
            select(Shift).where(Shift.school_level == school_level).order_by(Shift.name)
        ).all()
    )

    if shift_id is None and shifts:
        shift_id = shifts[0].id

    current_shift = db.get(Shift, shift_id) if shift_id else None
    if current_shift and current_shift.school_level != school_level:
        current_shift = None
        shift_id = None

    if current_shift:
        classes = list(
            db.scalars(
                select(SchoolClass)
                .where(SchoolClass.shift_id == current_shift.id)
                .order_by(SchoolClass.grade, SchoolClass.name)
            ).all()
        )
    else:
        classes = list(
            db.scalars(
                select(SchoolClass)
                .where(SchoolClass.school_level == school_level)
                .order_by(SchoolClass.grade, SchoolClass.name)
            ).all()
        )

    settings = db.scalars(
        select(ScheduleSettings).where(ScheduleSettings.school_level == school_level)
    ).first()

    if current_shift:
        working_days = current_shift.working_days
        max_lessons = current_shift.max_lessons_per_day
        lessons_range = list(
            range(
                current_shift.start_lesson,
                current_shift.start_lesson + current_shift.lessons_count,
            )
        )
    else:
        working_days = 5
        max_lessons = 7
        lessons_range = list(range(1, max_lessons + 1))

    class_ids = [c.id for c in classes]
    if class_ids:
        cells = list(
            db.execute(
                select(ScheduleCell)
                .options(*_CELL_LOAD)
                .where(ScheduleCell.class_id.in_(class_ids))
            )
            .scalars()
            .unique()
            .all()
        )
    else:
        cells = []

    lesson_times_by_day: dict[int, dict[int, str]] = {}
    class_hour_time_label = ""
    if current_shift:
        for lt in current_shift.lesson_times.all():
            lesson_times_by_day.setdefault(lt.day_of_week, {})[lt.lesson_number] = (
                f"{_fmt_time(lt.time_start)}–{_fmt_time(lt.time_end)}"
            )
        if current_shift.class_hour_start and current_shift.class_hour_end:
            class_hour_time_label = (
                f"{_fmt_time(current_shift.class_hour_start)}–"
                f"{_fmt_time(current_shift.class_hour_end)}"
            )

    raw_warnings = AutoScheduler(db).get_classroom_warnings(school_level)
    warnings = [
        ClassroomWarningOut(type=t, message=msg) for (t, msg, _entity) in raw_warnings
    ]

    return ScheduleGridOut(
        school_level=school_level,
        current_shift_id=current_shift.id if current_shift else None,
        current_shift=_shift_to_brief(current_shift) if current_shift else None,
        shifts=[_shift_to_brief(s) for s in shifts],
        classes=[SchoolClassRow.model_validate(c) for c in classes],
        day_names=_DAY_NAMES,
        working_days=working_days,
        max_lessons=max_lessons,
        lessons_range=lessons_range,
        lesson_times_by_day=lesson_times_by_day,
        class_hour_time_label=class_hour_time_label,
        cells=[_cell_to_out(c) for c in cells],
        classroom_warnings=warnings,
        settings=(
            ScheduleSettingsOut.model_validate(settings) if settings else None
        ),
    )


@router.get(
    "/assignments-for-class/{class_id}",
    response_model=AssignmentsForClassOut,
)
def assignments_for_class(
    class_id: int, db: Session = Depends(get_db)
) -> AssignmentsForClassOut:
    assignments = list(
        db.execute(
            select(TeachingAssignment)
            .options(
                joinedload(TeachingAssignment.subject),
                joinedload(TeachingAssignment.teacher),
            )
            .where(
                TeachingAssignment.class_id == class_id,
                TeachingAssignment.teacher_id.isnot(None),
            )
        )
        .scalars()
        .unique()
        .all()
    )
    result: list[AssignmentChoiceOut] = []
    for a in assignments:
        remaining = a.remaining_hours
        if remaining <= 0:
            continue
        subj = a.subject
        teacher = a.teacher
        result.append(
            AssignmentChoiceOut(
                id=a.id,
                subject_id=subj.id if subj else 0,
                subject_name=subj.display_name if subj else "?",
                subject_color=(subj.display_color if subj else "#3498db"),
                teacher_id=teacher.id if teacher else None,
                teacher_name=teacher.display_name if teacher else None,
                group_number=a.group_number,
                remaining_hours=remaining,
                preferred_classroom_id=a.preferred_classroom_id,
            )
        )

    classrooms = list(
        db.scalars(select(Classroom).order_by(Classroom.number)).all()
    )
    return AssignmentsForClassOut(
        assignments=result,
        classrooms=[ClassroomChoiceOut.model_validate(r) for r in classrooms],
    )


@router.post("/cells", response_model=ScheduleCellOut, status_code=201)
def create_cell(
    body: ScheduleCellCreate, db: Session = Depends(get_db)
) -> ScheduleCellOut:
    assignment = db.get(TeachingAssignment, body.assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    if db.get(SchoolClass, body.class_id) is None:
        raise HTTPException(status_code=404, detail="Class not found")
    if assignment.class_id != body.class_id:
        raise HTTPException(
            status_code=422,
            detail={"errors": ["Этот предмет назначен другому классу"]},
        )
    if body.classroom_id is not None and db.get(Classroom, body.classroom_id) is None:
        raise HTTPException(status_code=404, detail="Classroom not found")

    _ = assignment.school_class, assignment.teacher, assignment.subject
    errors = ScheduleValidator(db).validate_cell(
        assignment=assignment,
        day=body.day_of_week,
        lesson=body.lesson_number,
        classroom_id=body.classroom_id,
    )
    if errors:
        raise HTTPException(status_code=422, detail={"errors": errors})

    cell = ScheduleCell(
        class_id=body.class_id,
        day_of_week=body.day_of_week,
        lesson_number=body.lesson_number,
        assignment_id=body.assignment_id,
        classroom_id=body.classroom_id,
    )
    db.add(cell)
    db.commit()
    return _cell_to_out(_reload_cell(db, cell.id))


@router.patch("/cells/{cell_id}", response_model=ScheduleCellOut)
def move_cell(
    cell_id: int, body: ScheduleCellMove, db: Session = Depends(get_db)
) -> ScheduleCellOut:
    cell = db.get(ScheduleCell, cell_id)
    if cell is None:
        raise HTTPException(status_code=404, detail="Cell not found")

    new_class_id = body.class_id if body.class_id is not None else cell.class_id
    if body.class_id is not None and db.get(SchoolClass, body.class_id) is None:
        raise HTTPException(status_code=404, detail="Class not found")

    new_classroom_id = cell.classroom_id
    if body.set_classroom:
        new_classroom_id = body.classroom_id
        if new_classroom_id is not None and db.get(Classroom, new_classroom_id) is None:
            raise HTTPException(status_code=404, detail="Classroom not found")

    assignment = cell.assignment
    if new_class_id != assignment.class_id:
        assignment_for_target = db.scalars(
            select(TeachingAssignment).where(
                TeachingAssignment.class_id == new_class_id,
                TeachingAssignment.subject_id == assignment.subject_id,
                TeachingAssignment.teacher_id == assignment.teacher_id,
                TeachingAssignment.group_number == assignment.group_number,
            )
        ).first()
        if assignment_for_target is None:
            raise HTTPException(
                status_code=422,
                detail={
                    "errors": [
                        "У целевого класса нет такого назначения (предмет/учитель/группа)."
                    ]
                },
            )
        validation_assignment = assignment_for_target
    else:
        validation_assignment = assignment

    _ = (
        validation_assignment.school_class,
        validation_assignment.teacher,
        validation_assignment.subject,
    )
    errors = ScheduleValidator(db).validate_cell(
        assignment=validation_assignment,
        day=body.day_of_week,
        lesson=body.lesson_number,
        classroom_id=new_classroom_id,
        exclude_cell_id=cell_id,
    )
    if errors:
        raise HTTPException(status_code=422, detail={"errors": errors})

    cell.day_of_week = body.day_of_week
    cell.lesson_number = body.lesson_number
    if body.class_id is not None and new_class_id != cell.class_id:
        cell.class_id = new_class_id
        cell.assignment_id = validation_assignment.id
    if body.set_classroom:
        cell.classroom_id = new_classroom_id
    db.commit()
    return _cell_to_out(_reload_cell(db, cell.id))


@router.delete("/cells/{cell_id}", status_code=204, response_class=Response)
def delete_cell(cell_id: int, db: Session = Depends(get_db)) -> Response:
    cell = db.get(ScheduleCell, cell_id)
    if cell is None:
        raise HTTPException(status_code=404, detail="Cell not found")
    db.delete(cell)
    db.commit()
    return Response(status_code=204)


@router.get("/auto/page-data", response_model=AutoPageData)
def auto_page_data(db: Session = Depends(get_db)) -> AutoPageData:
    teachers = list(db.scalars(select(Teacher).order_by(Teacher.full_name)).all())
    classes = list(
        db.scalars(
            select(SchoolClass).order_by(SchoolClass.grade, SchoolClass.name)
        ).all()
    )
    scheduler = AutoScheduler(db)
    elementary_warnings = [
        ClassroomWarningOut(type=t, message=m)
        for (t, m, _e) in scheduler.get_classroom_warnings("elementary")
    ]
    secondary_warnings = [
        ClassroomWarningOut(type=t, message=m)
        for (t, m, _e) in scheduler.get_classroom_warnings("secondary")
    ]
    elementary_settings = db.scalars(
        select(ScheduleSettings).where(ScheduleSettings.school_level == "elementary")
    ).first()
    secondary_settings = db.scalars(
        select(ScheduleSettings).where(ScheduleSettings.school_level == "secondary")
    ).first()
    shifts_el = list(
        db.scalars(
            select(Shift).where(Shift.school_level == "elementary").order_by(Shift.name)
        ).all()
    )
    shifts_se = list(
        db.scalars(
            select(Shift).where(Shift.school_level == "secondary").order_by(Shift.name)
        ).all()
    )
    return AutoPageData(
        teachers=[TeacherBrief.model_validate(t) for t in teachers],
        classes=[SchoolClassRow.model_validate(c) for c in classes],
        elementary_warnings=elementary_warnings,
        secondary_warnings=secondary_warnings,
        elementary_settings=(
            ScheduleSettingsOut.model_validate(elementary_settings)
            if elementary_settings
            else None
        ),
        secondary_settings=(
            ScheduleSettingsOut.model_validate(secondary_settings)
            if secondary_settings
            else None
        ),
        shifts_elementary=[_shift_to_brief(s) for s in shifts_el],
        shifts_secondary=[_shift_to_brief(s) for s in shifts_se],
    )


def _ndjson_response(events_factory) -> StreamingResponse:
    """Stream NDJSON from AutoScheduler using a dedicated SQLAlchemy session."""

    def gen():
        db = SessionLocal()
        try:
            for event in events_factory(db):
                yield (
                    json.dumps(event, ensure_ascii=False) + "\n"
                ).encode("utf-8")
        except Exception as exc:  # noqa: BLE001 — broadcast errors to client
            yield (
                json.dumps(
                    {"type": "error", "message": str(exc)}, ensure_ascii=False
                )
                + "\n"
            ).encode("utf-8")
        finally:
            db.close()

    return StreamingResponse(
        gen(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/auto/all/stream")
def auto_all_stream(body: AutoAllStreamBody) -> StreamingResponse:
    def events(db: Session):
        scheduler = AutoScheduler(db)
        for event in scheduler.auto_schedule_all_iter(
            body.school_level,
            solver=body.solver,
            shift_id=body.shift_id,
            time_limit_sec=body.time_limit_sec,
            random_seed=body.random_seed,
        ):
            if event.get("type") == "done" and not body.diagnose:
                event.pop("diagnostics", None)
            yield event

    return _ndjson_response(events)


@router.post("/auto/by-teacher/stream")
def auto_by_teacher_stream(body: AutoByTeacherStreamBody) -> StreamingResponse:
    def events(db: Session):
        scheduler = AutoScheduler(db)
        for event in scheduler.schedule_by_teacher_ladder_iter(
            body.teacher_id, body.school_level
        ):
            if event.get("type") == "done" and not body.diagnose:
                event.pop("diagnostics", None)
            yield event

    return _ndjson_response(events)


@router.post("/clear", response_model=ClearScheduleResult)
def clear_schedule(
    body: ClearScheduleBody, db: Session = Depends(get_db)
) -> ClearScheduleResult:
    scheduler = AutoScheduler(db)
    count = scheduler.clear_schedule(
        school_level=body.school_level,
        class_id=body.class_id,
        teacher_id=body.teacher_id,
    )
    return ClearScheduleResult(count=count)


@router.get("/settings", response_model=SettingsPair)
def get_settings(db: Session = Depends(get_db)) -> SettingsPair:
    el = db.scalars(
        select(ScheduleSettings).where(ScheduleSettings.school_level == "elementary")
    ).first()
    se = db.scalars(
        select(ScheduleSettings).where(ScheduleSettings.school_level == "secondary")
    ).first()
    return SettingsPair(
        elementary=ScheduleSettingsOut.model_validate(el) if el else None,
        secondary=ScheduleSettingsOut.model_validate(se) if se else None,
    )


@router.put("/settings/{school_level}", response_model=ScheduleSettingsOut)
def update_settings(
    school_level: str, body: SettingsUpdate, db: Session = Depends(get_db)
) -> ScheduleSettingsOut:
    if school_level not in ("elementary", "secondary"):
        raise HTTPException(status_code=400, detail="Invalid school_level")
    s = db.scalars(
        select(ScheduleSettings).where(ScheduleSettings.school_level == school_level)
    ).first()
    if s is None:
        s = ScheduleSettings(school_level=school_level)
        db.add(s)
    s.max_lessons_per_subject_per_day = body.max_lessons_per_subject_per_day
    s.classroom_mode = body.classroom_mode
    if school_level == "elementary" and body.elementary_group_subjects_leave is not None:
        s.elementary_group_subjects_leave = body.elementary_group_subjects_leave
    db.commit()
    db.refresh(s)
    return ScheduleSettingsOut.model_validate(s)
