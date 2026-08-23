"""Reports & Excel exports."""
from __future__ import annotations

import io
from urllib.parse import quote

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import School, ScheduleCell, SchoolClass, Subject, Teacher, TeachingAssignment

from backend.deps import get_current_school, get_db, school_owned
from backend.schemas.reports import ClassReportOut, ReportCellOut, TeacherReportOut

router = APIRouter()

_DAY_NAMES = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"]
_XLSX_MIME = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

_CELL_LOAD = (
    joinedload(ScheduleCell.assignment).joinedload(TeachingAssignment.subject),
    joinedload(ScheduleCell.assignment).joinedload(TeachingAssignment.teacher),
    joinedload(ScheduleCell.classroom),
    joinedload(ScheduleCell.school_class),
)


def _fmt_time(t) -> str | None:
    if t is None:
        return None
    return t.strftime("%H:%M") if hasattr(t, "strftime") else str(t)


def _cell_to_report(cell: ScheduleCell) -> ReportCellOut:
    a = cell.assignment
    subj = a.subject if a else None
    teacher = a.teacher if a else None
    return ReportCellOut(
        id=cell.id,
        day_of_week=cell.day_of_week,
        lesson_number=cell.lesson_number,
        subject_name=subj.display_name if subj else "?",
        subject_color=(subj.display_color if subj else Subject.DEFAULT_COLOR),
        teacher_name=teacher.display_name if teacher else None,
        class_name=cell.school_class.name if cell.school_class else "?",
        classroom_name=cell.classroom.display_name if cell.classroom else None,
        group_number=a.group_number if a else None,
    )


def _load_cells(db: Session, *where) -> list[ScheduleCell]:
    stmt = select(ScheduleCell).options(*_CELL_LOAD)
    for clause in where:
        stmt = stmt.where(clause)
    return list(db.execute(stmt).scalars().unique().all())


@router.get("/class/{class_id}", response_model=ClassReportOut)
def class_report(class_id: int, db: Session = Depends(get_db),
    school: School = Depends(get_current_school)) -> ClassReportOut:
    school_class = school_owned(db, SchoolClass, class_id, school.id)

    shift = school_class.shift if school_class.shift_id else None
    working_days = shift.working_days if shift else 5
    max_lessons = shift.max_lessons_per_day if shift else 7
    lessons_range = (
        list(range(shift.start_lesson, shift.start_lesson + shift.lessons_count))
        if shift
        else list(range(1, max_lessons + 1))
    )

    lesson_times_by_day: dict[int, dict[int, str]] = {}
    class_hour_time_label: str | None = None
    if shift:
        for lt in shift.lesson_times.all():
            lesson_times_by_day.setdefault(lt.day_of_week, {})[lt.lesson_number] = (
                f"{_fmt_time(lt.time_start)}–{_fmt_time(lt.time_end)}"
            )
        if shift.class_hour_start and shift.class_hour_end:
            class_hour_time_label = (
                f"{_fmt_time(shift.class_hour_start)}–{_fmt_time(shift.class_hour_end)}"
            )

    cells = _load_cells(
        db,
        ScheduleCell.class_id == class_id,
        ScheduleCell.school_id == school.id,
    )
    return ClassReportOut(
        class_id=school_class.id,
        class_name=school_class.name,
        school_level=school_class.school_level,
        day_names=_DAY_NAMES,
        working_days=working_days,
        max_lessons=max_lessons,
        lessons_range=lessons_range,
        class_hour_day=shift.class_hour_day if shift else None,
        class_hour_time_label=class_hour_time_label,
        lesson_times_by_day=lesson_times_by_day,
        cells=[_cell_to_report(c) for c in cells],
    )


@router.get("/teacher/{teacher_id}", response_model=TeacherReportOut)
def teacher_report(teacher_id: int, db: Session = Depends(get_db),
    school: School = Depends(get_current_school)) -> TeacherReportOut:
    teacher = school_owned(db, Teacher, teacher_id, school.id)

    cells = list(
        db.execute(
            select(ScheduleCell)
            .join(TeachingAssignment)
            .options(*_CELL_LOAD)
            .where(
            TeachingAssignment.teacher_id == teacher_id,
            ScheduleCell.school_id == school.id,
        )
        )
        .scalars()
        .unique()
        .all()
    )
    working_days = 5
    max_lessons = 7
    for cell in cells:
        sh = cell.school_class.shift if cell.school_class.shift_id else None
        if sh:
            working_days = max(working_days, sh.working_days)
            max_lessons = max(max_lessons, sh.max_lessons_per_day)

    return TeacherReportOut(
        teacher_id=teacher.id,
        teacher_name=teacher.full_name,
        day_names=_DAY_NAMES,
        working_days=working_days,
        max_lessons=max_lessons,
        cells=[_cell_to_report(c) for c in cells],
    )


def _xlsx_stream(buf: io.BytesIO, filename: str) -> StreamingResponse:
    buf.seek(0)
    safe = quote(filename)
    return StreamingResponse(
        buf,
        media_type=_XLSX_MIME,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{safe}",
        },
    )


@router.get("/export/class/{class_id}")
def export_class(class_id: int, db: Session = Depends(get_db),
    school: School = Depends(get_current_school)) -> StreamingResponse:
    school_class = school_owned(db, SchoolClass, class_id, school.id)
    shift = school_class.shift if school_class.shift_id else None
    working_days = shift.working_days if shift else 5
    max_lessons = shift.max_lessons_per_day if shift else 7

    cells = _load_cells(
        db,
        ScheduleCell.class_id == class_id,
        ScheduleCell.school_id == school.id,
    )
    data = []
    for day in range(1, working_days + 1):
        for lesson in range(1, max_lessons + 1):
            row = {"День": _DAY_NAMES[day - 1], "Урок": lesson}
            match = [
                c for c in cells if c.day_of_week == day and c.lesson_number == lesson
            ]
            if match:
                row["Предмет"] = " / ".join(c.subject.display_name for c in match)
                row["Учитель"] = " / ".join(
                    (c.teacher.display_name if c.teacher else "—") for c in match
                )
                row["Кабинет"] = " / ".join(
                    (c.classroom.number if c.classroom else "—") for c in match
                )
            else:
                row["Предмет"] = ""
                row["Учитель"] = ""
                row["Кабинет"] = ""
            data.append(row)

    df = pd.DataFrame(data)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=f"Расписание {school_class.name}"[:31], index=False)
    return _xlsx_stream(buf, f"расписание_{school_class.name}.xlsx")


@router.get("/export/teacher/{teacher_id}")
def export_teacher(teacher_id: int, db: Session = Depends(get_db),
    school: School = Depends(get_current_school)) -> StreamingResponse:
    teacher = school_owned(db, Teacher, teacher_id, school.id)
    cells = list(
        db.execute(
            select(ScheduleCell)
            .join(TeachingAssignment)
            .options(*_CELL_LOAD)
            .where(
            TeachingAssignment.teacher_id == teacher_id,
            ScheduleCell.school_id == school.id,
        )
        )
        .scalars()
        .unique()
        .all()
    )
    working_days = 5
    max_lessons = 7
    for cell in cells:
        sh = cell.school_class.shift if cell.school_class.shift_id else None
        if sh:
            working_days = max(working_days, sh.working_days)
            max_lessons = max(max_lessons, sh.max_lessons_per_day)

    data = []
    for day in range(1, working_days + 1):
        for lesson in range(1, max_lessons + 1):
            row = {"День": _DAY_NAMES[day - 1], "Урок": lesson}
            match = [
                c for c in cells if c.day_of_week == day and c.lesson_number == lesson
            ]
            if match:
                row["Класс"] = " / ".join(c.school_class.name for c in match)
                row["Предмет"] = " / ".join(c.subject.display_name for c in match)
                row["Кабинет"] = " / ".join(
                    (c.classroom.number if c.classroom else "—") for c in match
                )
            else:
                row["Класс"] = ""
                row["Предмет"] = ""
                row["Кабинет"] = ""
            data.append(row)

    df = pd.DataFrame(data)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=f"Расписание {teacher.full_name}"[:31], index=False)
    filename = teacher.full_name.replace(" ", "_").replace(".", "")
    return _xlsx_stream(buf, f"расписание_{filename}.xlsx")


@router.get("/export/all/{school_level}")
def export_all(school_level: str, db: Session = Depends(get_db),
    school: School = Depends(get_current_school)) -> StreamingResponse:
    if school_level not in ("elementary", "secondary"):
        raise HTTPException(status_code=400, detail="Invalid school_level")
    classes = list(
        db.scalars(
            select(SchoolClass)
            .where(
                SchoolClass.school_level == school_level,
                SchoolClass.school_id == school.id,
            )
            .order_by(SchoolClass.grade, SchoolClass.name)
        ).all()
    )

    working_days = 5
    max_lessons = 7
    for c in classes:
        sh = c.shift if c.shift_id else None
        if sh:
            working_days = max(working_days, sh.working_days)
            max_lessons = max(max_lessons, sh.max_lessons_per_day)

    short_days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб"]
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for day in range(1, working_days + 1):
            sheet: dict[str, list] = {"Урок": list(range(1, max_lessons + 1))}
            for school_class in classes:
                cells = _load_cells(
                    db,
                    ScheduleCell.class_id == school_class.id,
                    ScheduleCell.day_of_week == day,
                    ScheduleCell.school_id == school.id,
                )
                column = []
                for lesson in range(1, max_lessons + 1):
                    match = [c for c in cells if c.lesson_number == lesson]
                    if match:
                        text = []
                        for cell in match:
                            label = cell.subject.name
                            if cell.assignment.group_number:
                                label += f"(гр.{cell.assignment.group_number})"
                            text.append(label)
                        column.append("\n".join(text))
                    else:
                        column.append("")
                sheet[school_class.name] = column
            pd.DataFrame(sheet).to_excel(writer, sheet_name=short_days[day - 1], index=False)

    level_name = "начальная" if school_level == "elementary" else "основная"
    return _xlsx_stream(buf, f"расписание_{level_name}_школа.xlsx")
