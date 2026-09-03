"""Schedule read queries."""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.domain import (
    DAY_NAMES,
    break_between_labels,
    fmt_time,
    interior_gap_lessons,
    lesson_end_exclusive,
    minutes_phrase,
    slot_facts_conflict,
    split_time_range,
    time_range_label,
)
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
from app.services.classroom_resolver import (
    filter_free_classrooms,
    get_classroom_warnings,
    load_settings,
)
from app.services.schedule_fact_loader import (
    candidate_slot_fact,
    load_classroom_busy,
    occupancy_fact_from_cell,
)
from app.services.bell_schedule import get_interval_for_slot
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
    TeacherDayData,
    TeacherDayLessonData,
    TeacherDayOccupantData,
    TeacherDayShiftData,
    TeacherRemainingClassData,
    TeacherRemainingData,
    TeacherRemainingSubjectData,
    _shift_brief,
    _warnings,
)
from app.services.schedule_mapping import CELL_LOAD, cell_to_schedule_dict
from app.services.tenancy import require_owned

_NONE_SHIFT_NAME = "без смены"


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
            teacher_remaining=self._teacher_remaining(school_level),
        )

    def _teacher_remaining(self, school_level: str) -> list[TeacherRemainingData]:
        """Unplaced hours per teacher at this school level, grouped by class."""
        assignments = list(
            self.db.execute(
                select(TeachingAssignment)
                .options(
                    joinedload(TeachingAssignment.subject),
                    joinedload(TeachingAssignment.teacher),
                    joinedload(TeachingAssignment.school_class),
                )
                .join(SchoolClass, TeachingAssignment.class_id == SchoolClass.id)
                .where(
                    TeachingAssignment.school_id == self.school_id,
                    SchoolClass.school_level == school_level,
                    TeachingAssignment.teacher_id.isnot(None),
                )
            )
            .scalars()
            .unique()
            .all()
        )
        counts = placed_counts(self.db, [a.id for a in assignments])
        teachers: dict[int, dict] = {}
        for assignment in assignments:
            teacher = assignment.teacher
            if teacher is None:
                continue
            school_class = assignment.school_class
            remaining = remaining_for(assignment, placed=counts.get(assignment.id, 0))
            bucket = teachers.setdefault(
                teacher.id,
                {
                    "teacher_id": teacher.id,
                    "teacher_name": teacher.display_name,
                    "remaining_hours": 0,
                    "classes": {},
                },
            )
            bucket["remaining_hours"] += remaining
            if remaining <= 0 or school_class is None:
                continue
            class_bucket = bucket["classes"].setdefault(
                school_class.id,
                {
                    "class_id": school_class.id,
                    "class_name": school_class.name,
                    "grade": school_class.grade,
                    "remaining_hours": 0,
                    "subjects": [],
                },
            )
            class_bucket["remaining_hours"] += remaining
            subj = assignment.subject
            class_bucket["subjects"].append(
                TeacherRemainingSubjectData(
                    subject_name=subj.display_name if subj else "?",
                    remaining_hours=remaining,
                    group_number=assignment.group_number,
                )
            )
        rows: list[TeacherRemainingData] = []
        for bucket in teachers.values():
            classes = [
                TeacherRemainingClassData(
                    class_id=item["class_id"],
                    class_name=item["class_name"],
                    remaining_hours=item["remaining_hours"],
                    subjects=sorted(
                        item["subjects"],
                        key=lambda s: (s.subject_name, s.group_number or 0),
                    ),
                )
                for item in sorted(
                    bucket["classes"].values(),
                    key=lambda c: (c["grade"], c["class_name"], c["class_id"]),
                )
            ]
            rows.append(
                TeacherRemainingData(
                    teacher_id=bucket["teacher_id"],
                    teacher_name=bucket["teacher_name"],
                    remaining_hours=bucket["remaining_hours"],
                    classes=classes,
                )
            )
        rows.sort(key=lambda r: (r.teacher_name, r.teacher_id))
        return rows

    def assignments_for_class(
        self,
        class_id: int,
        day: int | None = None,
        lesson: int | None = None,
    ) -> AssignmentsForClassData:
        school_class = require_owned(self.db, SchoolClass, class_id, self.school_id)
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
                    requires_fixed_classroom=bool(
                        subj.requires_fixed_classroom if subj else False
                    ),
                )
            )
        classrooms = list(
            self.db.scalars(
                select(Classroom)
                .options(selectinload(Classroom.subjects))
                .where(Classroom.school_id == self.school_id)
                .order_by(Classroom.number)
            ).all()
        )
        if day is not None and lesson is not None:
            slot = candidate_slot_fact(
                self.db,
                class_id=class_id,
                day=day,
                lesson=lesson,
                shift_id=school_class.shift_id,
            )
            busy = load_classroom_busy(self.db, {c.id for c in classrooms})
            classrooms = filter_free_classrooms(
                classrooms, slot=slot, classroom_busy=busy
            )
        return AssignmentsForClassData(
            assignments=result,
            classrooms=[classroom_choice(c) for c in classrooms],
        )

    def teacher_day(
        self,
        teacher_id: int,
        day: int,
        class_id: int | None = None,
        lesson: int | None = None,
    ) -> TeacherDayData:
        """One weekday of a teacher across shifts (for the add-lesson modal)."""
        teacher = require_owned(self.db, Teacher, teacher_id, self.school_id)
        school_class = (
            require_owned(self.db, SchoolClass, class_id, self.school_id)
            if class_id is not None
            else None
        )
        current_shift_id = school_class.shift_id if school_class else None
        candidate = None
        if class_id is not None and lesson is not None:
            candidate = candidate_slot_fact(
                self.db,
                class_id=class_id,
                day=day,
                lesson=lesson,
                shift_id=current_shift_id,
            )

        cells = list(
            self.db.execute(
                select(ScheduleCell)
                .options(
                    *CELL_LOAD,
                    joinedload(ScheduleCell.school_class).joinedload(
                        SchoolClass.shift
                    ),
                )
                .join(TeachingAssignment)
                .where(
                    TeachingAssignment.teacher_id == teacher.id,
                    ScheduleCell.day_of_week == day,
                    ScheduleCell.school_id == self.school_id,
                )
            )
            .scalars()
            .unique()
            .all()
        )

        by_shift_lesson: dict[tuple[int | None, int], list[ScheduleCell]] = (
            defaultdict(list)
        )
        for cell in cells:
            sc = cell.school_class
            sid = sc.shift_id if sc else None
            by_shift_lesson[(sid, cell.lesson_number)].append(cell)

        shift_by_id: dict[int, Shift] = {
            shift.id: shift
            for shift in self.db.scalars(
                select(Shift)
                .where(Shift.school_id == self.school_id)
                .order_by(Shift.name)
            ).all()
        }

        has_none = any(sid is None for sid, _ in by_shift_lesson) or (
            school_class is not None and school_class.shift_id is None
        )
        columns: list[tuple[int | None, str, bool, Shift | None]] = [
            (shift.id, shift.name, shift.id == current_shift_id, shift)
            for shift in sorted(shift_by_id.values(), key=lambda s: s.name)
        ]
        if has_none:
            columns.append(
                (None, _NONE_SHIFT_NAME, current_shift_id is None, None)
            )

        timed_others: list[tuple[str, str, str]] = []
        has_other_occupied = False
        shifts_out: list[TeacherDayShiftData] = []
        for sid, name, is_current, shift in columns:
            extra = {ln for (s, ln) in by_shift_lesson if s == sid}
            if is_current and lesson is not None:
                extra.add(lesson)
            lesson_nums = _shift_day_lessons(shift, day, extra)
            occupied_nums = {
                ln for ln in extra if by_shift_lesson.get((sid, ln))
            }
            gaps = interior_gap_lessons(occupied_nums)
            rows: list[TeacherDayLessonData] = []
            for ln in lesson_nums:
                occupants_cells = by_shift_lesson.get((sid, ln), [])
                occupants = [_occupant_from_cell(c) for c in occupants_cells]
                time_label = _lesson_time_label(self.db, shift, sid, day, ln)
                if occupants_cells and not is_current:
                    has_other_occupied = True
                overlaps = False
                if candidate is not None and occupants_cells:
                    facts = [
                        occupancy_fact_from_cell(cell, self.db)
                        for cell in occupants_cells
                    ]
                    overlaps = any(
                        slot_facts_conflict(candidate, fact) for fact in facts
                    )
                    if not is_current and time_label and not overlaps:
                        timed_others.append(
                            (occupants[0].class_name, name, time_label)
                        )
                is_candidate = bool(
                    is_current
                    and candidate is not None
                    and ln == candidate.lesson
                )
                rows.append(
                    TeacherDayLessonData(
                        lesson=ln,
                        time_label=time_label,
                        is_candidate=is_candidate,
                        is_gap=ln in gaps,
                        overlaps_current=overlaps,
                        occupants=occupants,
                    )
                )
            shifts_out.append(
                TeacherDayShiftData(
                    shift_id=sid,
                    shift_name=name,
                    is_current=is_current,
                    lessons=rows,
                )
            )

        other_shift_gap = _other_shift_gap_text(
            candidate,
            timed_others,
            has_other_occupied=has_other_occupied,
        )
        day_name = DAY_NAMES[day - 1] if 1 <= day <= len(DAY_NAMES) else str(day)
        return TeacherDayData(
            teacher_id=teacher.id,
            teacher_name=teacher.display_name,
            day_of_week=day,
            day_name=day_name,
            other_shift_gap=other_shift_gap,
            shifts=shifts_out,
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
        days_of_week: list[int] | None = None,
    ) -> int:
        return self.delete_cells(
            school_level=school_level,
            class_id=class_id,
            teacher_id=teacher_id,
            days_of_week=days_of_week,
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


def _shift_day_lessons(
    shift: Shift | None, day: int, extra: set[int]
) -> list[int]:
    nums: list[int] = []
    if shift is not None:
        if shift.class_hour_day == day and (
            shift.class_hour_start or 0 in extra
        ):
            nums.append(0)
        start = max(1, int(shift.start_lesson or 1))
        nums.extend(range(start, lesson_end_exclusive(shift, day)))
    for n in sorted(extra):
        if n not in nums:
            nums.append(n)
    return nums


def _lesson_time_label(
    db: Session,
    shift: Shift | None,
    shift_id: int | None,
    day: int,
    lesson: int,
) -> str | None:
    sid = shift.id if shift is not None else shift_id
    interval = get_interval_for_slot(sid, lesson, day, session=db)
    if interval is None:
        return None
    return time_range_label(interval[0], interval[1])


def _occupant_from_cell(cell: ScheduleCell) -> TeacherDayOccupantData:
    a = cell.assignment
    subj = a.subject if a else None
    sc = cell.school_class
    return TeacherDayOccupantData(
        class_id=cell.class_id,
        class_name=sc.name if sc else "?",
        subject_name=subj.display_name if subj else "?",
        subject_color=(subj.display_color if subj else Subject.DEFAULT_COLOR),
        classroom_name=cell.classroom.display_name if cell.classroom else None,
        group_number=a.group_number if a else None,
    )


def _other_shift_gap_text(
    candidate,
    timed_others: list[tuple[str, str, str]],
    *,
    has_other_occupied: bool,
) -> str | None:
    if not has_other_occupied:
        return "В других сменах в этот день свободен"
    if candidate is None or candidate.interval is None or not timed_others:
        return None
    cand_label = time_range_label(candidate.interval[0], candidate.interval[1])
    if not cand_label:
        return None
    best: tuple[int, str] | None = None
    cand_start = fmt_time(candidate.interval[0])
    for class_name, shift_name, time_label in timed_others:
        after_other = break_between_labels(time_label, cand_label)
        if after_other:
            minutes, _ = after_other
            parts = split_time_range(time_label)
            other_end = parts[1] if parts else ""
            msg = (
                f"После {class_name} ({other_end}), {shift_name} "
                f"до этого слота ({cand_start}) — {minutes_phrase(minutes)}"
            )
            if best is None or minutes < best[0]:
                best = (minutes, msg)
            continue
        after_slot = break_between_labels(cand_label, time_label)
        if after_slot:
            minutes, _ = after_slot
            parts = split_time_range(time_label)
            other_start = parts[0] if parts else ""
            cand_end = fmt_time(candidate.interval[1])
            msg = (
                f"После этого слота ({cand_end}) до {class_name} "
                f"({other_start}), {shift_name} — {minutes_phrase(minutes)}"
            )
            if best is None or minutes < best[0]:
                best = (minutes, msg)
    return best[1] if best else None



