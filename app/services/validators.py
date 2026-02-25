"""
Schedule validation service
"""
from app.models import ScheduleCell, TeachingAssignment, ScheduleSettings, Classroom


class ScheduleValidator:
    """Validates schedule for conflicts"""

    def validate_cell(self, assignment, day, lesson, classroom_id=None, exclude_cell_id=None):
        """
        Validate if a lesson can be placed at the given slot.
        Returns list of error messages (empty if valid).
        """
        errors = []

        # Check teacher conflict
        if assignment.teacher_id:
            if self.check_teacher_conflict(assignment.teacher_id, day, lesson, exclude_cell_id):
                errors.append(f'Учитель {assignment.teacher.display_name} уже занят в это время')

        # Check classroom conflict
        if classroom_id:
            if self.check_classroom_conflict(classroom_id, day, lesson, exclude_cell_id):
                errors.append('Кабинет уже занят в это время')

        # Check class conflict (except for groups)
        class_conflict = self.check_class_conflict(
            assignment.class_id, day, lesson, 
            assignment.group_number, exclude_cell_id
        )
        if class_conflict:
            errors.append('Класс уже занят в это время')

        # Check max lessons per subject per day
        if self.check_subject_per_day_limit(assignment, day, exclude_cell_id):
            errors.append('Достигнут лимит уроков по этому предмету в этот день')

        return errors

    def check_subject_per_day_limit(self, assignment, day, exclude_cell_id=None):
        """
        Check if placing another lesson would exceed max lessons per subject per day.
        Returns True if limit exceeded.
        """
        settings = ScheduleSettings.query.filter_by(
            school_level=assignment.school_class.school_level
        ).first()
        max_per_day = settings.max_lessons_per_subject_per_day if settings else 2

        query = ScheduleCell.query.filter(
            ScheduleCell.assignment_id == assignment.id,
            ScheduleCell.day_of_week == day
        )
        if exclude_cell_id:
            query = query.filter(ScheduleCell.id != exclude_cell_id)
        count = query.count()
        return count >= max_per_day

    def check_teacher_conflict(self, teacher_id, day, lesson, exclude_cell_id=None):
        """Check if teacher has another lesson at this time"""
        query = ScheduleCell.query.join(TeachingAssignment).filter(
            TeachingAssignment.teacher_id == teacher_id,
            ScheduleCell.day_of_week == day,
            ScheduleCell.lesson_number == lesson
        )
        if exclude_cell_id:
            query = query.filter(ScheduleCell.id != exclude_cell_id)
        return query.first() is not None

    def check_classroom_conflict(self, classroom_id, day, lesson, exclude_cell_id=None):
        """
        Check if classroom is occupied at this time.
        Takes into account classes_capacity: e.g. спортзал может вмещать несколько классов.
        """
        if not classroom_id:
            return False
        classroom = Classroom.query.get(classroom_id)
        cap = (classroom.classes_capacity or 1) if classroom else 1
        query = ScheduleCell.query.filter(
            ScheduleCell.classroom_id == classroom_id,
            ScheduleCell.day_of_week == day,
            ScheduleCell.lesson_number == lesson
        )
        if exclude_cell_id:
            query = query.filter(ScheduleCell.id != exclude_cell_id)
        count = query.count()
        return count >= cap

    def check_class_conflict(self, class_id, day, lesson, group_number=None, exclude_cell_id=None):
        """
        Check if class is occupied at this time.
        Groups can be scheduled simultaneously.
        """
        query = ScheduleCell.query.join(TeachingAssignment).filter(
            ScheduleCell.class_id == class_id,
            ScheduleCell.day_of_week == day,
            ScheduleCell.lesson_number == lesson
        )
        if exclude_cell_id:
            query = query.filter(ScheduleCell.id != exclude_cell_id)

        existing = query.all()

        if not existing:
            return False

        # If adding a group lesson, check if existing are also groups
        if group_number:
            for cell in existing:
                if cell.assignment.group_number is None:
                    # Whole class is scheduled - conflict
                    return True
                if cell.assignment.group_number == group_number:
                    # Same group already scheduled - conflict
                    return True
            # Different group can be added
            return False

        # Adding whole class, but groups are scheduled - conflict
        return True

    def get_teacher_windows(self, teacher_id, working_days=5):
        """
        Get 'windows' (gaps) in teacher's schedule.
        Returns list of (day, lesson) where teacher has a gap between lessons.
        """
        windows = []
        cells = ScheduleCell.query.join(TeachingAssignment).filter(
            TeachingAssignment.teacher_id == teacher_id
        ).order_by(ScheduleCell.day_of_week, ScheduleCell.lesson_number).all()

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
