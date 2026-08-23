"""Reports and Excel export business logic."""
from __future__ import annotations

import io
from dataclasses import dataclass

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import DAY_NAMES, SHORT_DAY_NAMES, time_range_label
from app.models import ScheduleCell, SchoolClass, Teacher, TeachingAssignment
from app.services.errors import BadRequestError
from app.services.schedule_mapping import (
    CELL_LOAD_WITH_CLASS,
    cell_to_report_dict,
    load_cells,
)
from app.services.tenancy import require_owned


@dataclass(frozen=True)
class ExportFile:
    buffer: io.BytesIO
    filename: str


class ReportService:
    def __init__(self, db: Session, school_id: int):
        self.db = db
        self.school_id = school_id

    def class_report(self, class_id: int) -> dict:
        school_class = require_owned(self.db, SchoolClass, class_id, self.school_id)

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
                label = time_range_label(lt.time_start, lt.time_end)
                if label:
                    lesson_times_by_day.setdefault(lt.day_of_week, {})[lt.lesson_number] = (
                        label
                    )
            class_hour_time_label = time_range_label(
                shift.class_hour_start, shift.class_hour_end
            )

        cells = load_cells(
            self.db,
            ScheduleCell.class_id == class_id,
            ScheduleCell.school_id == self.school_id,
            with_class=True,
        )
        return {
            "class_id": school_class.id,
            "class_name": school_class.name,
            "school_level": school_class.school_level,
            "day_names": DAY_NAMES,
            "working_days": working_days,
            "max_lessons": max_lessons,
            "lessons_range": lessons_range,
            "class_hour_day": shift.class_hour_day if shift else None,
            "class_hour_time_label": class_hour_time_label,
            "lesson_times_by_day": lesson_times_by_day,
            "cells": [cell_to_report_dict(c) for c in cells],
        }

    def teacher_report(self, teacher_id: int) -> dict:
        teacher = require_owned(self.db, Teacher, teacher_id, self.school_id)

        cells = list(
            self.db.execute(
                select(ScheduleCell)
                .join(TeachingAssignment)
                .options(*CELL_LOAD_WITH_CLASS)
                .where(
                    TeachingAssignment.teacher_id == teacher_id,
                    ScheduleCell.school_id == self.school_id,
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

        return {
            "teacher_id": teacher.id,
            "teacher_name": teacher.full_name,
            "day_names": DAY_NAMES,
            "working_days": working_days,
            "max_lessons": max_lessons,
            "cells": [cell_to_report_dict(c) for c in cells],
        }

    def export_class(self, class_id: int) -> ExportFile:
        school_class = require_owned(self.db, SchoolClass, class_id, self.school_id)
        shift = school_class.shift if school_class.shift_id else None
        working_days = shift.working_days if shift else 5
        max_lessons = shift.max_lessons_per_day if shift else 7

        cells = load_cells(
            self.db,
            ScheduleCell.class_id == class_id,
            ScheduleCell.school_id == self.school_id,
            with_class=True,
        )
        data = []
        for day in range(1, working_days + 1):
            for lesson in range(1, max_lessons + 1):
                row = {"День": DAY_NAMES[day - 1], "Урок": lesson}
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
            df.to_excel(
                writer, sheet_name=f"Расписание {school_class.name}"[:31], index=False
            )
        return ExportFile(buf, f"расписание_{school_class.name}.xlsx")

    def export_teacher(self, teacher_id: int) -> ExportFile:
        teacher = require_owned(self.db, Teacher, teacher_id, self.school_id)
        cells = list(
            self.db.execute(
                select(ScheduleCell)
                .join(TeachingAssignment)
                .options(*CELL_LOAD_WITH_CLASS)
                .where(
                    TeachingAssignment.teacher_id == teacher_id,
                    ScheduleCell.school_id == self.school_id,
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
                row = {"День": DAY_NAMES[day - 1], "Урок": lesson}
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
            df.to_excel(
                writer, sheet_name=f"Расписание {teacher.full_name}"[:31], index=False
            )
        filename = teacher.full_name.replace(" ", "_").replace(".", "")
        return ExportFile(buf, f"расписание_{filename}.xlsx")

    def export_all(self, school_level: str) -> ExportFile:
        if school_level not in ("elementary", "secondary"):
            raise BadRequestError("Invalid school_level")
        classes = list(
            self.db.scalars(
                select(SchoolClass)
                .where(
                    SchoolClass.school_level == school_level,
                    SchoolClass.school_id == self.school_id,
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

        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            for day in range(1, working_days + 1):
                sheet: dict[str, list] = {"Урок": list(range(1, max_lessons + 1))}
                for school_class in classes:
                    cells = load_cells(
                        self.db,
                        ScheduleCell.class_id == school_class.id,
                        ScheduleCell.day_of_week == day,
                        ScheduleCell.school_id == self.school_id,
                        with_class=True,
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
                pd.DataFrame(sheet).to_excel(
                    writer, sheet_name=SHORT_DAY_NAMES[day - 1], index=False
                )

        level_name = "начальная" if school_level == "elementary" else "основная"
        return ExportFile(buf, f"расписание_{level_name}_школа.xlsx")
