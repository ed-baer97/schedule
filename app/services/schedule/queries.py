"""Schedule read queries."""
from __future__ import annotations

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
from app.services.dto import (
    classroom_choice,
    school_class_row,
    settings_data,
    teacher_brief,
)
from app.services.errors import BadRequestError
from app.services.schedule.types import (
    AssignmentChoiceData,
    AssignmentsForClassData,
    AutoPageDataRaw,
    GridData,
    SettingsPairData,
    ShiftBriefData,
    _shift_brief,
    _warnings,
)
from app.services.schedule_mapping import CELL_LOAD, cell_to_schedule_dict
from app.services.tenancy import require_owned


class ScheduleQueriesMixin:
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

        return GridData(
            school_level=school_level,
            current_shift_id=current_shift.id if current_shift else None,
            current_shift=_shift_brief(current_shift) if current_shift else None,
            shifts=[_shift_brief(s) for s in shifts],
            classes=[school_class_row(c) for c in classes],
            day_names=DAY_NAMES,
            working_days=working_days,
            max_lessons=max_lessons,
            lessons_range=lessons_range,
            lesson_times_by_day=lesson_times_by_day,
            class_hour_time_label=class_hour_time_label,
            cells=[cell_to_schedule_dict(c) for c in cells],
            classroom_warnings=_warnings(raw_warnings),
            settings=settings_data(settings) if settings else None,
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
        return AssignmentsForClassData(
            assignments=result,
            classrooms=[classroom_choice(c) for c in classrooms],
        )

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
            teachers=[teacher_brief(t) for t in teachers],
            classes=[school_class_row(c) for c in classes],
            elementary_warnings=_warnings(
                get_classroom_warnings(self.db, self.school_id, "elementary")
            ),
            secondary_warnings=_warnings(
                get_classroom_warnings(self.db, self.school_id, "secondary")
            ),
            elementary_settings=(
                settings_data(elementary_settings) if elementary_settings else None
            ),
            secondary_settings=(
                settings_data(secondary_settings) if secondary_settings else None
            ),
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
        el = load_settings(self.db, self.school_id, "elementary")
        se = load_settings(self.db, self.school_id, "secondary")
        return SettingsPairData(
            elementary=settings_data(el) if el else None,
            secondary=settings_data(se) if se else None,
        )

    def update_settings(
        self,
        school_level: str,
        *,
        max_lessons_per_subject_per_day: int,
        classroom_mode: str,
        elementary_group_subjects_leave: bool | None = None,
        pref_teacher_gaps: int | None = None,
        pref_hard_subjects_early: int | None = None,
        pref_adjacent_pairs: int | None = None,
        pref_classroom_stability: int | None = None,
    ) -> ScheduleSettingsData:
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
        if pref_teacher_gaps is not None:
            s.pref_teacher_gaps = pref_teacher_gaps
        if pref_hard_subjects_early is not None:
            s.pref_hard_subjects_early = pref_hard_subjects_early
        if pref_adjacent_pairs is not None:
            s.pref_adjacent_pairs = pref_adjacent_pairs
        if pref_classroom_stability is not None:
            s.pref_classroom_stability = pref_classroom_stability
        self.db.commit()
        self.db.refresh(s)
        return settings_data(s)


