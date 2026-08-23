"""
Schedule validation service
"""
from sqlalchemy.orm import Session

from app.models import ScheduleCell, TeachingAssignment, ScheduleSettings, Classroom, SchoolClass, Shift
from app.services.bell_schedule import schedules_conflict
from app.services.session_util import resolve_session


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

    def __init__(self, session: Session | None = None, school_id: int | None = None):
        self.session = resolve_session(session)
        self.school_id = school_id

    def _settings_for(self, school_level: str):
        q = self.session.query(ScheduleSettings).filter_by(school_level=school_level)
        if self.school_id is not None:
            q = q.filter_by(school_id=self.school_id)
        return q.first()

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

        if exclude_cell_id is None and assignment.remaining_hours <= 0:
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
            class_id, day, lesson,
            assignment.group_number, exclude_cell_id
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
        return count >= max_per_day

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
        return count >= 2

    def check_teacher_conflict(self, teacher_id, day, lesson, exclude_cell_id=None, class_id=None):
        """Return the conflicting cell if the teacher is busy, otherwise None."""
        sc = self.session.get(SchoolClass, class_id) if class_id else None
        candidate_shift = sc.shift_id if sc else None

        query = self.session.query(ScheduleCell).join(TeachingAssignment).filter(
            TeachingAssignment.teacher_id == teacher_id,
            ScheduleCell.day_of_week == day,
        )
        if exclude_cell_id:
            query = query.filter(ScheduleCell.id != exclude_cell_id)

        for cell in query.all():
            if schedules_conflict(
                candidate_shift, lesson, day,
                cell.school_class.shift_id, cell.lesson_number, cell.day_of_week,
                session=self.session,
            ):
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

        sc = self.session.get(SchoolClass, class_id) if class_id else None
        candidate_shift = sc.shift_id if sc else None

        query = self.session.query(ScheduleCell).filter(
            ScheduleCell.classroom_id == classroom_id,
            ScheduleCell.day_of_week == day,
        )
        if exclude_cell_id:
            query = query.filter(ScheduleCell.id != exclude_cell_id)

        occupying = []
        for cell in query.all():
            if schedules_conflict(
                candidate_shift, lesson, day,
                cell.school_class.shift_id, cell.lesson_number, cell.day_of_week,
                session=self.session,
            ):
                occupying.append(cell)
        return occupying if len(occupying) >= cap else []

    def check_class_conflict(self, class_id, day, lesson, group_number=None, exclude_cell_id=None):
        """
        Return the occupying cell if the class is busy, otherwise None.
        Groups can be scheduled simultaneously when times do not overlap.
        """
        school_class = self.session.get(SchoolClass, class_id)
        candidate_shift = school_class.shift_id if school_class else None

        query = self.session.query(ScheduleCell).join(TeachingAssignment).filter(
            ScheduleCell.class_id == class_id,
            ScheduleCell.day_of_week == day,
        )
        if exclude_cell_id:
            query = query.filter(ScheduleCell.id != exclude_cell_id)

        for cell in query.all():
            if not schedules_conflict(
                candidate_shift, lesson, day,
                cell.school_class.shift_id, cell.lesson_number, cell.day_of_week,
                session=self.session,
            ):
                continue

            og = cell.assignment.group_number
            if group_number:
                if og is None or og == group_number:
                    return cell
            else:
                return cell

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
