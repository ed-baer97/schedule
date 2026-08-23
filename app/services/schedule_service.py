"""Schedule grid, cells, settings, and auto page data."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.domain import DAY_NAMES, time_range_label
from app.models import (
    Classroom,
    ScheduleCell,
    ScheduleSettings,
    SchoolClass,
    Shift,
    Subject,
    Teacher,
    TeachingAssignment,
)
from app.services.assignment_hours import placed_counts, remaining_for
from app.services.classroom_resolver import get_classroom_warnings, load_settings
from app.services.errors import BadRequestError, ValidationConflict
from app.services.schedule_mapping import CELL_LOAD, cell_to_schedule_dict, reload_cell
from app.services.tenancy import require_owned
from app.services.validators import ScheduleValidator


@dataclass
class ShiftBriefData:
    id: int
    name: str
    school_level: str
    working_days: int
    max_lessons_per_day: int
    start_lesson: int
    lessons_count: int
    class_hour_day: int | None = None
    class_hour_time_label: str | None = None


@dataclass
class AssignmentChoiceData:
    id: int
    subject_id: int
    subject_name: str
    subject_color: str
    teacher_id: int | None
    teacher_name: str | None
    group_number: int | None
    remaining_hours: int
    preferred_classroom_id: int | None


@dataclass
class Placement:
    """One schedule cell to insert (sole write-path for ScheduleCell rows)."""

    assignment_id: int
    class_id: int
    day_of_week: int
    lesson_number: int
    classroom_id: int | None = None


@dataclass
class GridData:
    school_level: str
    current_shift_id: int | None
    current_shift: ShiftBriefData | None
    shifts: list[ShiftBriefData]
    classes: list[SchoolClass]
    day_names: list[str]
    working_days: int
    max_lessons: int
    lessons_range: list[int]
    lesson_times_by_day: dict[int, dict[int, str]]
    class_hour_time_label: str
    cells: list[dict]
    classroom_warnings: list[tuple[str, str]]
    settings: ScheduleSettings | None


@dataclass
class AssignmentsForClassData:
    assignments: list[AssignmentChoiceData]
    classrooms: list[Classroom]


@dataclass
class AutoPageDataRaw:
    teachers: list[Teacher]
    classes: list[SchoolClass]
    elementary_warnings: list[tuple[str, str]]
    secondary_warnings: list[tuple[str, str]]
    elementary_settings: ScheduleSettings | None
    secondary_settings: ScheduleSettings | None
    shifts_elementary: list[ShiftBriefData]
    shifts_secondary: list[ShiftBriefData]


@dataclass
class SettingsPairData:
    elementary: ScheduleSettings | None
    secondary: ScheduleSettings | None


def _shift_brief(s: Shift) -> ShiftBriefData:
    return ShiftBriefData(
        id=s.id,
        name=s.name,
        school_level=s.school_level,
        working_days=s.working_days,
        max_lessons_per_day=s.max_lessons_per_day,
        start_lesson=s.start_lesson,
        lessons_count=s.lessons_count,
        class_hour_day=s.class_hour_day,
        class_hour_time_label=time_range_label(s.class_hour_start, s.class_hour_end),
    )


class ScheduleService:
    def __init__(self, db: Session, school_id: int):
        self.db = db
        self.school_id = school_id
        self.validator = ScheduleValidator(db, school_id=school_id)

    def get_grid(
        self, school_level: str, shift_id: int | None = None
    ) -> GridData:
        shifts = list(
            self.db.scalars(
                select(Shift)
                .where(
                    Shift.school_level == school_level,
                    Shift.school_id == self.school_id,
                )
                .order_by(Shift.name)
            ).all()
        )

        if shift_id is None and shifts:
            shift_id = shifts[0].id

        current_shift = self.db.get(Shift, shift_id) if shift_id else None
        if current_shift is not None and current_shift.school_id != self.school_id:
            current_shift = None
            shift_id = None
        if current_shift and current_shift.school_level != school_level:
            current_shift = None
            shift_id = None

        if current_shift:
            classes = list(
                self.db.scalars(
                    select(SchoolClass)
                    .where(
                        SchoolClass.shift_id == current_shift.id,
                        SchoolClass.school_id == self.school_id,
                    )
                    .order_by(SchoolClass.grade, SchoolClass.name)
                ).all()
            )
        else:
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

        settings = self.db.scalars(
            select(ScheduleSettings).where(
                ScheduleSettings.school_level == school_level,
                ScheduleSettings.school_id == self.school_id,
            )
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
                self.db.execute(
                    select(ScheduleCell)
                    .options(*CELL_LOAD)
                    .where(
                        ScheduleCell.class_id.in_(class_ids),
                        ScheduleCell.school_id == self.school_id,
                    )
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
                label = time_range_label(lt.time_start, lt.time_end)
                if label:
                    lesson_times_by_day.setdefault(lt.day_of_week, {})[
                        lt.lesson_number
                    ] = label
            class_hour_time_label = (
                time_range_label(
                    current_shift.class_hour_start, current_shift.class_hour_end
                )
                or ""
            )

        raw_warnings = get_classroom_warnings(
            self.db, self.school_id, school_level
        )
        warnings = [(t, msg) for (t, msg, _entity) in raw_warnings]

        return GridData(
            school_level=school_level,
            current_shift_id=current_shift.id if current_shift else None,
            current_shift=_shift_brief(current_shift) if current_shift else None,
            shifts=[_shift_brief(s) for s in shifts],
            classes=classes,
            day_names=DAY_NAMES,
            working_days=working_days,
            max_lessons=max_lessons,
            lessons_range=lessons_range,
            lesson_times_by_day=lesson_times_by_day,
            class_hour_time_label=class_hour_time_label,
            cells=[cell_to_schedule_dict(c) for c in cells],
            classroom_warnings=warnings,
            settings=settings,
        )

    def assignments_for_class(self, class_id: int) -> AssignmentsForClassData:
        require_owned(self.db, SchoolClass, class_id, self.school_id)
        assignments = list(
            self.db.execute(
                select(TeachingAssignment)
                .options(
                    joinedload(TeachingAssignment.subject),
                    joinedload(TeachingAssignment.teacher),
                )
                .where(
                    TeachingAssignment.class_id == class_id,
                    TeachingAssignment.school_id == self.school_id,
                    TeachingAssignment.teacher_id.isnot(None),
                )
            )
            .scalars()
            .unique()
            .all()
        )
        counts = placed_counts(self.db, [a.id for a in assignments])
        result: list[AssignmentChoiceData] = []
        for a in assignments:
            remaining = remaining_for(a, placed=counts.get(a.id, 0))
            if remaining <= 0:
                continue
            subj = a.subject
            teacher = a.teacher
            result.append(
                AssignmentChoiceData(
                    id=a.id,
                    subject_id=subj.id if subj else 0,
                    subject_name=subj.display_name if subj else "?",
                    subject_color=(
                        subj.display_color if subj else Subject.DEFAULT_COLOR
                    ),
                    teacher_id=teacher.id if teacher else None,
                    teacher_name=teacher.display_name if teacher else None,
                    group_number=a.group_number,
                    remaining_hours=remaining,
                    preferred_classroom_id=a.preferred_classroom_id,
                )
            )
        classrooms = list(
            self.db.scalars(
                select(Classroom)
                .where(Classroom.school_id == self.school_id)
                .order_by(Classroom.number)
            ).all()
        )
        return AssignmentsForClassData(assignments=result, classrooms=classrooms)

    def insert_cell(
        self,
        *,
        class_id: int,
        day_of_week: int,
        lesson_number: int,
        assignment_id: int,
        classroom_id: int | None = None,
        validate: bool = False,
        commit: bool = False,
    ) -> ScheduleCell:
        """Single write-path for ScheduleCell (manual grid, auto, solver)."""
        cell = ScheduleCell(
            school_id=self.school_id,
            class_id=class_id,
            day_of_week=day_of_week,
            lesson_number=lesson_number,
            assignment_id=assignment_id,
            classroom_id=classroom_id,
        )
        if validate:
            assignment = require_owned(
                self.db, TeachingAssignment, assignment_id, self.school_id
            )
            require_owned(self.db, SchoolClass, class_id, self.school_id)
            if classroom_id is not None:
                require_owned(self.db, Classroom, classroom_id, self.school_id)
            _ = assignment.school_class, assignment.teacher, assignment.subject
            errors = self.validator.validate_cell(
                assignment=assignment,
                day=day_of_week,
                lesson=lesson_number,
                classroom_id=classroom_id,
            )
            if errors:
                raise ValidationConflict(errors)
        self.db.add(cell)
        if commit:
            self.db.commit()
        else:
            self.db.flush()
        return cell

    def apply_placements(
        self,
        placements: list[Placement],
        *,
        validate: bool = False,
        commit: bool = True,
    ) -> int:
        """Insert many cells via insert_cell; one commit for the batch."""
        count = 0
        for p in placements:
            self.insert_cell(
                class_id=p.class_id,
                day_of_week=p.day_of_week,
                lesson_number=p.lesson_number,
                assignment_id=p.assignment_id,
                classroom_id=p.classroom_id,
                validate=validate,
                commit=False,
            )
            count += 1
        if commit:
            self.db.commit()
        else:
            self.db.flush()
        return count

    def create_cell(
        self,
        *,
        class_id: int,
        day_of_week: int,
        lesson_number: int,
        assignment_id: int,
        classroom_id: int | None,
    ) -> dict:
        assignment = require_owned(
            self.db, TeachingAssignment, assignment_id, self.school_id
        )
        require_owned(self.db, SchoolClass, class_id, self.school_id)
        if assignment.class_id != class_id:
            raise ValidationConflict(["Этот предмет назначен другому классу"])
        if classroom_id is not None:
            require_owned(self.db, Classroom, classroom_id, self.school_id)

        _ = assignment.school_class, assignment.teacher, assignment.subject
        errors = self.validator.validate_cell(
            assignment=assignment,
            day=day_of_week,
            lesson=lesson_number,
            classroom_id=classroom_id,
        )
        if errors:
            raise ValidationConflict(errors)

        cell = self.insert_cell(
            class_id=class_id,
            day_of_week=day_of_week,
            lesson_number=lesson_number,
            assignment_id=assignment_id,
            classroom_id=classroom_id,
            validate=False,
            commit=True,
        )
        return cell_to_schedule_dict(reload_cell(self.db, cell.id))

    def move_cell(
        self,
        cell_id: int,
        *,
        day_of_week: int,
        lesson_number: int,
        class_id: int | None = None,
        classroom_id: int | None = None,
        set_classroom: bool = False,
    ) -> dict:
        cell = require_owned(self.db, ScheduleCell, cell_id, self.school_id)

        new_class_id = class_id if class_id is not None else cell.class_id
        if class_id is not None:
            require_owned(self.db, SchoolClass, class_id, self.school_id)

        new_classroom_id = cell.classroom_id
        if set_classroom:
            new_classroom_id = classroom_id
            if new_classroom_id is not None:
                require_owned(self.db, Classroom, new_classroom_id, self.school_id)

        assignment = cell.assignment
        if new_class_id != assignment.class_id:
            assignment_for_target = self.db.scalars(
                select(TeachingAssignment).where(
                    TeachingAssignment.class_id == new_class_id,
                    TeachingAssignment.subject_id == assignment.subject_id,
                    TeachingAssignment.teacher_id == assignment.teacher_id,
                    TeachingAssignment.group_number == assignment.group_number,
                    TeachingAssignment.school_id == self.school_id,
                )
            ).first()
            if assignment_for_target is None:
                raise ValidationConflict(
                    [
                        "У целевого класса нет такого назначения (предмет/учитель/группа)."
                    ]
                )
            validation_assignment = assignment_for_target
        else:
            validation_assignment = assignment

        _ = (
            validation_assignment.school_class,
            validation_assignment.teacher,
            validation_assignment.subject,
        )
        errors = self.validator.validate_cell(
            assignment=validation_assignment,
            day=day_of_week,
            lesson=lesson_number,
            classroom_id=new_classroom_id,
            exclude_cell_id=cell_id,
        )
        if errors:
            raise ValidationConflict(errors)

        cell.day_of_week = day_of_week
        cell.lesson_number = lesson_number
        if class_id is not None and new_class_id != cell.class_id:
            cell.class_id = new_class_id
            cell.assignment_id = validation_assignment.id
        if set_classroom:
            cell.classroom_id = new_classroom_id
        self.db.commit()
        return cell_to_schedule_dict(reload_cell(self.db, cell.id))

    def delete_cell(self, cell_id: int) -> None:
        cell = require_owned(self.db, ScheduleCell, cell_id, self.school_id)
        self.db.delete(cell)
        self.db.commit()

    def reposition_cell(
        self,
        cell_id: int,
        *,
        day_of_week: int,
        lesson_number: int,
        classroom_id: int | None = None,
        set_classroom: bool = False,
        validate: bool = False,
        commit: bool = False,
    ) -> ScheduleCell:
        """Move a cell to another slot (solver/auto path; no commit by default)."""
        cell = require_owned(self.db, ScheduleCell, cell_id, self.school_id)
        new_classroom_id = classroom_id if set_classroom else cell.classroom_id
        if validate:
            assignment = cell.assignment
            _ = assignment.school_class, assignment.teacher, assignment.subject
            errors = self.validator.validate_cell(
                assignment=assignment,
                day=day_of_week,
                lesson=lesson_number,
                classroom_id=new_classroom_id,
                exclude_cell_id=cell_id,
            )
            if errors:
                raise ValidationConflict(errors)
        cell.day_of_week = day_of_week
        cell.lesson_number = lesson_number
        if set_classroom:
            cell.classroom_id = new_classroom_id
        if commit:
            self.db.commit()
        else:
            self.db.flush()
        return cell

    def delete_cells(
        self,
        *,
        class_ids: list[int] | None = None,
        cell_ids: list[int] | None = None,
        teacher_id: int | None = None,
        school_level: str | None = None,
        class_id: int | None = None,
        commit: bool = False,
    ) -> int:
        """Batch-delete ScheduleCell rows scoped to this school."""
        stmt = select(ScheduleCell).where(ScheduleCell.school_id == self.school_id)
        if cell_ids is not None:
            if not cell_ids:
                return 0
            stmt = stmt.where(ScheduleCell.id.in_(cell_ids))
        if class_ids is not None:
            if not class_ids:
                return 0
            stmt = stmt.where(ScheduleCell.class_id.in_(class_ids))
        if class_id is not None:
            stmt = stmt.where(ScheduleCell.class_id == class_id)
        elif school_level is not None:
            stmt = stmt.join(SchoolClass).where(
                SchoolClass.school_level == school_level,
                SchoolClass.school_id == self.school_id,
            )
        if teacher_id is not None:
            stmt = stmt.join(
                TeachingAssignment,
                TeachingAssignment.id == ScheduleCell.assignment_id,
            ).where(TeachingAssignment.teacher_id == teacher_id)

        cells = list(self.db.scalars(stmt).unique().all())
        count = len(cells)
        for cell in cells:
            self.db.delete(cell)
        if count:
            if commit:
                self.db.commit()
            else:
                self.db.flush()
        return count

    def auto_page_data(self) -> AutoPageDataRaw:
        teachers = list(
            self.db.scalars(
                select(Teacher)
                .where(Teacher.school_id == self.school_id)
                .order_by(Teacher.full_name)
            ).all()
        )
        classes = list(
            self.db.scalars(
                select(SchoolClass)
                .where(SchoolClass.school_id == self.school_id)
                .order_by(SchoolClass.grade, SchoolClass.name)
            ).all()
        )
        elementary_warnings = [
            (t, m)
            for (t, m, _e) in get_classroom_warnings(
                self.db, self.school_id, "elementary"
            )
        ]
        secondary_warnings = [
            (t, m)
            for (t, m, _e) in get_classroom_warnings(
                self.db, self.school_id, "secondary"
            )
        ]
        elementary_settings = load_settings(self.db, self.school_id, "elementary")
        secondary_settings = load_settings(self.db, self.school_id, "secondary")
        shifts_el = list(
            self.db.scalars(
                select(Shift)
                .where(
                    Shift.school_level == "elementary",
                    Shift.school_id == self.school_id,
                )
                .order_by(Shift.name)
            ).all()
        )
        shifts_se = list(
            self.db.scalars(
                select(Shift)
                .where(
                    Shift.school_level == "secondary",
                    Shift.school_id == self.school_id,
                )
                .order_by(Shift.name)
            ).all()
        )
        return AutoPageDataRaw(
            teachers=teachers,
            classes=classes,
            elementary_warnings=elementary_warnings,
            secondary_warnings=secondary_warnings,
            elementary_settings=elementary_settings,
            secondary_settings=secondary_settings,
            shifts_elementary=[_shift_brief(s) for s in shifts_el],
            shifts_secondary=[_shift_brief(s) for s in shifts_se],
        )

    def clear_schedule(
        self,
        school_level: str | None = None,
        class_id: int | None = None,
        teacher_id: int | None = None,
    ) -> int:
        return self.delete_cells(
            school_level=school_level,
            class_id=class_id,
            teacher_id=teacher_id,
            commit=True,
        )

    def get_settings(self) -> SettingsPairData:
        return SettingsPairData(
            elementary=load_settings(self.db, self.school_id, "elementary"),
            secondary=load_settings(self.db, self.school_id, "secondary"),
        )

    def update_settings(
        self,
        school_level: str,
        *,
        max_lessons_per_subject_per_day: int,
        classroom_mode: str,
        elementary_group_subjects_leave: bool | None = None,
    ) -> ScheduleSettings:
        if school_level not in ("elementary", "secondary"):
            raise BadRequestError("Invalid school_level")
        s = load_settings(self.db, self.school_id, school_level)
        if s is None:
            s = ScheduleSettings(school_id=self.school_id, school_level=school_level)
            self.db.add(s)
        s.max_lessons_per_subject_per_day = max_lessons_per_subject_per_day
        s.classroom_mode = classroom_mode
        if school_level == "elementary" and elementary_group_subjects_leave is not None:
            s.elementary_group_subjects_leave = elementary_group_subjects_leave
        self.db.commit()
        self.db.refresh(s)
        return s

