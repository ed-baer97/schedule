"""
Schedule validation service
"""
from sqlalchemy.orm import Session

from app.domain.assignment import hours_exhausted
from app.domain.schedule_facts import UnitFact
from app.domain.schedule_rules import (
    occupancy_blocks_unit,
    overlapping_classroom_busy,
    slot_facts_conflict,
    subject_day_limit_reached,
    teacher_class_day_limit_reached,
)
from app.models import ScheduleCell, TeachingAssignment, Classroom, SchoolClass, Shift
from app.services.assignment_hours import placed_count
from app.services.classroom_resolver import load_settings
from app.services.schedule_fact_loader import (
    candidate_slot_fact,
    candidate_unit_fact,
    load_class_occupancy,
    load_classroom_busy,
    load_teacher_busy,
)


def _lesson_word(lesson: int) -> str:
    return "классный час" if lesson == 0 else f"урок {lesson}"


def _cell_brief(cell: ScheduleCell) -> str:
    assignment = cell.assignment
    subject_name = "?"
    group = ""
    if assignment:
        if assignment.subject:
            subject_name = assignment.subject.display_name
        if assignment.group_number:
            group = f" (гр.{assignment.group_number})"
    class_name = cell.school_class.name if cell.school_class else "?"
    return f"{subject_name}{group} у {class_name} ({_lesson_word(cell.lesson_number)})"


class ScheduleValidator:
    """Validates schedule for conflicts"""

    def __init__(self, session: Session, school_id: int):
        self.session = session
        self.school_id = school_id

    def _settings_for(self, school_level: str):
        return load_settings(self.session, self.school_id, school_level)

    def _candidate_slot(self, class_id, day, lesson):
        sc = self.session.get(SchoolClass, class_id) if class_id else None
        shift_id = sc.shift_id if sc else None
        return candidate_slot_fact(
            self.session,
            class_id=class_id or 0,
            day=day,
            lesson=lesson,
            shift_id=shift_id,
        )

    def _cell_by_id(self, cell_id: int | None) -> ScheduleCell | None:
        if cell_id is None:
            return None
        return self.session.get(ScheduleCell, cell_id)

    def validate_cell(self, assignment, day, lesson, classroom_id=None, exclude_cell_id=None):
        """
        Validate if a lesson can be placed at the given slot.
        Returns list of error messages (empty if valid).
        """
        errors = []
        class_id = assignment.class_id

        if lesson == 0:
            sc = assignment.school_class
            sh = self.session.get(Shift, sc.shift_id) if sc and sc.shift_id else None
            if (
                not sh
                or sh.class_hour_day != day
                or not sh.class_hour_start
                or not sh.class_hour_end
            ):
                errors.append(
                    'Классный час не настроен для этой смены на выбранный день или не задано время'
                )
                return errors

        sc = assignment.school_class
        sh = self.session.get(Shift, sc.shift_id) if sc and sc.shift_id else None
        if sh and lesson != 0:
            if day > sh.working_days:
                errors.append('Выбранный день вне учебной недели для смены этого класса')
            if lesson > sh.max_lessons_per_day:
                errors.append('Номер урока больше сетки дня для этой смены')
            if lesson < sh.start_lesson or lesson >= sh.start_lesson + sh.lessons_count:
                errors.append('Номер урока вне интервала смены')

        if exclude_cell_id is None and hours_exhausted(
            assignment.hours_per_week, placed_count(self.session, assignment.id)
        ):
            subject_name = assignment.subject.display_name if assignment.subject else "предмет"
            errors.append(
                f'Все часы по предмету «{subject_name}» уже расставлены '
                f'({assignment.hours_per_week} ч/нед)'
            )

        if not assignment.teacher_id:
            errors.append('У назначения нет учителя — сначала назначьте учителя')

        # Check teacher conflict
        if assignment.teacher_id:
            busy = self.check_teacher_conflict(
                assignment.teacher_id, day, lesson, exclude_cell_id, class_id=class_id
            )
            if busy:
                teacher_name = assignment.teacher.display_name if assignment.teacher else "?"
                errors.append(
                    f'Учитель {teacher_name} уже занят в это время: {_cell_brief(busy)}'
                )

        # Check classroom conflict
        if classroom_id:
            occupying = self.check_classroom_conflict(
                classroom_id, day, lesson, exclude_cell_id, class_id=class_id
            )
            if occupying:
                classroom = self.session.get(Classroom, classroom_id)
                room_name = classroom.display_name if classroom else str(classroom_id)
                briefs = "; ".join(_cell_brief(c) for c in occupying)
                cap = (classroom.classes_capacity or 1) if classroom else 1
                if cap > 1:
                    errors.append(
                        f'Кабинет {room_name} заполнен (вместимость {cap}): {briefs}'
                    )
                else:
                    errors.append(f'Кабинет {room_name} уже занят в это время: {briefs}')

        # Check class conflict (except for groups)
        class_busy = self.check_class_conflict(
            class_id,
            day,
            lesson,
            assignment.group_number,
            exclude_cell_id,
            subject_id=assignment.subject_id,
            assignment=assignment,
        )
        if class_busy:
            errors.append(f'Класс уже занят в это время: {_cell_brief(class_busy)}')

        # Check max lessons per subject per day
        if self.check_subject_per_day_limit(assignment, day, exclude_cell_id):
            settings = (
                self._settings_for(assignment.school_class.school_level)
            )
            max_per_day = settings.max_lessons_per_subject_per_day if settings else 2
            subject_name = assignment.subject.display_name if assignment.subject else "предмет"
            errors.append(
                f'Достигнут лимит уроков по предмету «{subject_name}» в этот день '
                f'(не больше {max_per_day})'
            )

        # Check max lessons per teacher+class per day
        if self.check_teacher_class_per_day_limit(assignment, day, exclude_cell_id):
            teacher_name = assignment.teacher.display_name if assignment.teacher else "учитель"
            errors.append(
                f'Учитель {teacher_name} уже ведёт 2 урока в этом классе в этот день'
            )

        return errors

    def check_subject_per_day_limit(self, assignment, day, exclude_cell_id=None):
        """
        Check if placing another lesson would exceed max lessons per subject per day.
        Returns True if limit exceeded.
        """
        settings = (
            self._settings_for(assignment.school_class.school_level)
        )
        max_per_day = settings.max_lessons_per_subject_per_day if settings else 2

        query = self.session.query(ScheduleCell).filter(
            ScheduleCell.assignment_id == assignment.id,
            ScheduleCell.day_of_week == day
        )
        if exclude_cell_id:
            query = query.filter(ScheduleCell.id != exclude_cell_id)
        count = query.count()
        return subject_day_limit_reached(count, max_per_day)

    def check_teacher_class_per_day_limit(self, assignment, day, exclude_cell_id=None):
        """
        Check if placing another lesson would exceed max 2 lessons per day
        for the same teacher in the same class.
        Returns True if limit exceeded.
        """
        if not assignment.teacher_id:
            return False

        query = self.session.query(ScheduleCell).join(TeachingAssignment).filter(
            ScheduleCell.class_id == assignment.class_id,
            ScheduleCell.day_of_week == day,
            TeachingAssignment.teacher_id == assignment.teacher_id,
        )
        if exclude_cell_id:
            query = query.filter(ScheduleCell.id != exclude_cell_id)
        count = query.count()
        return teacher_class_day_limit_reached(count, 2)

    def check_teacher_conflict(self, teacher_id, day, lesson, exclude_cell_id=None, class_id=None):
        """Return the conflicting cell if the teacher is busy, otherwise None."""
        candidate_slot = self._candidate_slot(class_id, day, lesson)
        busy_map = load_teacher_busy(
            self.session,
            {teacher_id},
            exclude_cell_id=exclude_cell_id,
        )
        for fact in busy_map.get(teacher_id, []):
            if slot_facts_conflict(candidate_slot, fact):
                cell = self._cell_by_id(fact.source_cell_id)
                if cell is not None:
                    return cell
        return None

    def check_classroom_conflict(self, classroom_id, day, lesson, exclude_cell_id=None, class_id=None):
        """
        Return occupying cells if the classroom is at capacity, otherwise an empty list.
        Takes into account classes_capacity: e.g. спортзал может вмещать несколько классов.
        """
        if not classroom_id:
            return []
        classroom = self.session.get(Classroom, classroom_id)
        cap = (classroom.classes_capacity or 1) if classroom else 1

        candidate_slot = self._candidate_slot(class_id, day, lesson)
        busy_map = load_classroom_busy(
            self.session,
            {classroom_id},
            exclude_cell_id=exclude_cell_id,
        )
        overlapping = overlapping_classroom_busy(candidate_slot, classroom_id, busy_map)
        if len(overlapping) < cap:
            return []
        cells = []
        for fact in overlapping:
            cell = self._cell_by_id(fact.source_cell_id)
            if cell is not None:
                cells.append(cell)
        return cells

    def check_class_conflict(
        self,
        class_id,
        day,
        lesson,
        group_number=None,
        exclude_cell_id=None,
        subject_id=None,
        assignment=None,
    ):
        """
        Return the occupying cell if the class is busy, otherwise None.
        Uses the same occupancy_blocks_unit predicate as the CP-SAT builder.
        """
        school_class = self.session.get(SchoolClass, class_id)
        level = (
            school_class.school_level
            if school_class and school_class.school_level
            else "elementary"
        )
        if assignment is not None:
            unit = candidate_unit_fact(assignment)
        else:
            unit = UnitFact(
                unit_id="candidate",
                assignment_id=-1,
                teacher_id=None,
                class_id=class_id,
                subject_id=subject_id,
                group_number=group_number,
                school_level=level,
            )
        candidate_slot = self._candidate_slot(class_id, day, lesson)
        occupancy = load_class_occupancy(
            self.session,
            [class_id],
            exclude_cell_id=exclude_cell_id,
        )
        for occupied in occupancy.get(class_id, []):
            if occupancy_blocks_unit(unit, occupied, candidate_slot=candidate_slot):
                cell = self._cell_by_id(occupied.source_cell_id)
                if cell is not None:
                    return cell
                # Fallback if cell was deleted mid-check
                return None

        return None

    def get_teacher_windows(self, teacher_id, working_days=None):
        """
        Get 'windows' (gaps) in teacher's schedule.
        Returns list of (day, lesson) where teacher has a gap between lessons.
        """
        cells = (
            self.session.query(ScheduleCell)
            .join(TeachingAssignment)
            .filter(TeachingAssignment.teacher_id == teacher_id)
            .order_by(ScheduleCell.day_of_week, ScheduleCell.lesson_number)
            .all()
        )

        if working_days is None:
            wd_list = []
            for cell in cells:
                sc = cell.school_class
                sh = self.session.get(Shift, sc.shift_id) if sc and sc.shift_id else None
                if sh:
                    wd_list.append(sh.working_days)
            working_days = max(wd_list) if wd_list else 5

        windows = []

        # Group by day
        by_day = {}
        for cell in cells:
            if cell.day_of_week not in by_day:
                by_day[cell.day_of_week] = []
            by_day[cell.day_of_week].append(cell.lesson_number)

        # Find gaps
        for day in range(1, working_days + 1):
            if day not in by_day:
                continue
            lessons = sorted(set(by_day[day]))
            if len(lessons) < 2:
                continue
            for i in range(lessons[0] + 1, lessons[-1]):
                if i not in lessons:
                    windows.append((day, i))

        return windows
