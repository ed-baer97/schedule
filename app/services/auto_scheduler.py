"""
Automatic schedule generation service
"""
from app import db
from app.models import Teacher, SchoolClass, TeachingAssignment, ScheduleCell, ScheduleSettings
from app.services.validators import ScheduleValidator


class AutoScheduler:
    """
    Service for automatic schedule generation.
    Implements different strategies for scheduling.
    Supports: teacher_room (дети приходят к учителю), class_room (учитель приходит к классу).
    """

    def __init__(self):
        self.validator = ScheduleValidator()

    def _get_classroom_for_cell(self, assignment, school_level):
        """
        Определяет classroom_id для ячейки расписания.
        Приоритет: 1) предмет с фиксированным кабинетом, 2) групповой урок в началке, 3) сценарий.
        """
        subject = assignment.subject
        teacher = assignment.teacher
        school_class = assignment.school_class
        settings = ScheduleSettings.query.filter_by(school_level=school_level).first()

        # 1. Предмет с фиксированным кабинетом (Информатика, Физкультура, Технология)
        if subject.requires_fixed_classroom:
            return assignment.preferred_classroom_id or subject.default_classroom_id

        # 2. Началка + групповой предмет: дети уходят к учителю
        if (school_level == 'elementary'
            and settings and settings.elementary_group_subjects_leave
            and assignment.group_number is not None
            and teacher and teacher.home_classroom_id):
            return teacher.home_classroom_id

        # 3. Основной сценарий по настройкам уровня
        mode = settings.classroom_mode if settings else 'class_room'
        if mode == 'teacher_room' and teacher:
            return teacher.home_classroom_id
        if mode == 'class_room' and school_class:
            return school_class.home_classroom_id

        # Fallback: preferred из назначения
        return assignment.preferred_classroom_id

    def schedule_by_teacher_ladder(self, teacher_id, school_level='elementary'):
        """
        'Ladder' strategy: fill teacher's schedule sequentially
        to avoid 'windows' (gaps between lessons).
        
        Returns count of scheduled lessons.
        """
        settings = ScheduleSettings.query.filter_by(school_level=school_level).first()
        working_days = settings.working_days if settings else 5
        max_lessons = settings.max_lessons_per_day if settings else 7

        # Get unscheduled assignments for this teacher
        assignments = TeachingAssignment.query\
            .join(SchoolClass)\
            .filter(
                TeachingAssignment.teacher_id == teacher_id,
                SchoolClass.school_level == school_level
            ).all()

        # Filter to those with remaining hours
        to_schedule = []
        for a in assignments:
            remaining = a.remaining_hours
            if remaining > 0:
                to_schedule.extend([a] * remaining)

        if not to_schedule:
            return 0

        scheduled_count = 0
        current_day = 1
        current_lesson = 1

        for assignment in to_schedule:
            placed = False

            while not placed and current_day <= working_days:
                classroom_id = self._get_classroom_for_cell(assignment, school_level)
                errors = self.validator.validate_cell(
                    assignment=assignment,
                    day=current_day,
                    lesson=current_lesson,
                    classroom_id=classroom_id
                )

                if not errors:
                    cell = ScheduleCell(
                        class_id=assignment.class_id,
                        day_of_week=current_day,
                        lesson_number=current_lesson,
                        assignment_id=assignment.id,
                        classroom_id=classroom_id
                    )
                    db.session.add(cell)
                    scheduled_count += 1
                    placed = True

                    if assignment.group_number is not None:
                        scheduled_count += self._try_place_complementary_subgroup(
                            assignment, current_day, current_lesson, school_level
                        )

                # Move to next slot
                current_lesson += 1
                if current_lesson > max_lessons:
                    current_lesson = 1
                    current_day += 1

            if current_day > working_days:
                break

        db.session.commit()
        return scheduled_count

    def schedule_class_day(self, class_id, day, school_level='elementary'):
        """
        Fill one day for a class with available lessons.
        Distributes lessons evenly.
        
        Returns count of scheduled lessons.
        """
        settings = ScheduleSettings.query.filter_by(school_level=school_level).first()
        max_lessons = settings.max_lessons_per_day if settings else 7

        # Get unscheduled assignments for this class
        assignments = TeachingAssignment.query.filter(
            TeachingAssignment.class_id == class_id,
            TeachingAssignment.teacher_id.isnot(None)
        ).all()

        # Get assignments with remaining hours, sorted by remaining hours (most first)
        available = []
        for a in assignments:
            remaining = a.remaining_hours
            if remaining > 0:
                available.append((a, remaining))
        available.sort(key=lambda x: -x[1])

        scheduled_count = 0

        for lesson_num in range(1, max_lessons + 1):
            if not available:
                break

            for i, (assignment, remaining) in enumerate(available):
                classroom_id = self._get_classroom_for_cell(assignment, school_level)
                errors = self.validator.validate_cell(
                    assignment=assignment,
                    day=day,
                    lesson=lesson_num,
                    classroom_id=classroom_id
                )

                if not errors:
                    cell = ScheduleCell(
                        class_id=class_id,
                        day_of_week=day,
                        lesson_number=lesson_num,
                        assignment_id=assignment.id,
                        classroom_id=classroom_id
                    )
                    db.session.add(cell)
                    scheduled_count += 1

                    new_remaining = remaining - 1
                    if new_remaining <= 0:
                        available.pop(i)
                    else:
                        available[i] = (assignment, new_remaining)

                    if assignment.group_number is not None:
                        scheduled_count += self._place_complementary_in_slot(
                            available, assignment.group_number, class_id, day, lesson_num, school_level
                        )

                    break

        db.session.commit()
        return scheduled_count

    def _place_complementary_in_slot(self, available, placed_group_number, class_id, day, lesson_num, school_level='elementary'):
        """
        After placing a subgroup from the available list,
        find and place the complementary subgroup in the same slot.
        Returns 1 if placed, 0 otherwise.
        """
        for i, (assignment, remaining) in enumerate(available):
            if assignment.group_number is None:
                continue
            if assignment.group_number == placed_group_number:
                continue

            classroom_id = self._get_classroom_for_cell(assignment, school_level)
            errors = self.validator.validate_cell(
                assignment=assignment,
                day=day,
                lesson=lesson_num,
                classroom_id=classroom_id
            )
            if not errors:
                cell = ScheduleCell(
                    class_id=class_id,
                    day_of_week=day,
                    lesson_number=lesson_num,
                    assignment_id=assignment.id,
                    classroom_id=classroom_id
                )
                db.session.add(cell)

                new_remaining = remaining - 1
                if new_remaining <= 0:
                    available.pop(i)
                else:
                    available[i] = (assignment, new_remaining)
                return 1
        return 0

    def _try_place_complementary_subgroup(self, placed_assignment, day, lesson, school_level='elementary'):
        """
        After placing a subgroup in teacher-ladder mode,
        find and place the complementary subgroup (possibly from another teacher)
        in the same slot. Returns 1 if placed, 0 otherwise.
        """
        complementary_assignments = TeachingAssignment.query.filter(
            TeachingAssignment.class_id == placed_assignment.class_id,
            TeachingAssignment.group_number.isnot(None),
            TeachingAssignment.group_number != placed_assignment.group_number,
            TeachingAssignment.teacher_id.isnot(None)
        ).all()

        for comp in complementary_assignments:
            if comp.remaining_hours <= 0:
                continue
            classroom_id = self._get_classroom_for_cell(comp, school_level)
            errors = self.validator.validate_cell(
                assignment=comp,
                day=day,
                lesson=lesson,
                classroom_id=classroom_id
            )
            if not errors:
                cell = ScheduleCell(
                    class_id=comp.class_id,
                    day_of_week=day,
                    lesson_number=lesson,
                    assignment_id=comp.id,
                    classroom_id=classroom_id
                )
                db.session.add(cell)
                return 1
        return 0

    def auto_schedule_all(self, school_level='elementary'):
        """
        Automatically schedule all unscheduled lessons.
        Uses a combination of strategies.
        
        Returns total count of scheduled lessons.
        """
        settings = ScheduleSettings.query.filter_by(school_level=school_level).first()
        working_days = settings.working_days if settings else 5

        total_scheduled = 0

        # Get all classes for this level
        classes = SchoolClass.query.filter_by(school_level=school_level)\
            .order_by(SchoolClass.grade, SchoolClass.name).all()

        # Schedule day by day, class by class
        for day in range(1, working_days + 1):
            for school_class in classes:
                count = self.schedule_class_day(school_class.id, day, school_level)
                total_scheduled += count

        return total_scheduled

    def clear_schedule(self, school_level=None, class_id=None, teacher_id=None):
        """
        Clear schedule (delete cells) with optional filters.
        """
        query = ScheduleCell.query

        if class_id:
            query = query.filter(ScheduleCell.class_id == class_id)
        elif school_level:
            query = query.join(SchoolClass).filter(SchoolClass.school_level == school_level)

        if teacher_id:
            query = query.join(TeachingAssignment).filter(TeachingAssignment.teacher_id == teacher_id)

        cells = query.all()
        count = len(cells)
        for cell in cells:
            db.session.delete(cell)
        db.session.commit()
        return count

    def get_classroom_warnings(self, school_level=None):
        """
        Собирает предупреждения об уроках без привязки к кабинету.
        Returns: [(type, message, cell_or_entity), ...]
        """
        from app.models import Subject
        warnings = []
        seen = set()  # (type, id) для дедупликации

        if school_level:
            settings = ScheduleSettings.query.filter_by(school_level=school_level).first()
            mode = settings.classroom_mode if settings else 'class_room'
        else:
            settings = None
            mode = 'class_room'

        # Уроки без кабинета в расписании
        cells = ScheduleCell.query.filter(ScheduleCell.classroom_id.is_(None))
        if school_level:
            cells = cells.join(SchoolClass).filter(SchoolClass.school_level == school_level)
        for cell in cells.all():
            a = cell.assignment
            s = a.subject
            if s.requires_fixed_classroom and not (a.preferred_classroom_id or s.default_classroom_id):
                key = ('fixed_no_room', cell.class_id, s.id)
                if key not in seen:
                    seen.add(key)
                    warnings.append(('fixed_no_room', f'{cell.school_class.name} {s.name}: предмет требует кабинет', cell))
            elif mode == 'teacher_room' and a.teacher and not a.teacher.home_classroom_id:
                key = ('teacher_no_room', a.teacher_id)
                if key not in seen:
                    seen.add(key)
                    warnings.append(('teacher_no_room', f'{a.teacher.display_name} не имеет прикреплённого кабинета', cell))
            elif mode == 'class_room' and not cell.school_class.home_classroom_id:
                key = ('class_no_room', cell.class_id)
                if key not in seen:
                    seen.add(key)
                    warnings.append(('class_no_room', f'{cell.school_class.name} не имеет прикреплённого кабинета', cell))

        # Учителя без кабинета (для teacher_room) — если ещё нет уроков в расписании
        if school_level and mode == 'teacher_room':
            for t in Teacher.query.join(TeachingAssignment).join(SchoolClass).filter(
                SchoolClass.school_level == school_level,
                Teacher.home_classroom_id.is_(None)
            ).distinct().all():
                key = ('teacher_no_room', t.id)
                if key not in seen:
                    seen.add(key)
                    warnings.append(('teacher_no_room', f'Учитель {t.display_name} не имеет прикреплённого кабинета', t))

        # Классы без кабинета (для class_room)
        if school_level and mode == 'class_room':
            for c in SchoolClass.query.filter_by(school_level=school_level).filter(
                    SchoolClass.home_classroom_id.is_(None)).all():
                if c.assignments.filter(TeachingAssignment.teacher_id.isnot(None)).first():
                    key = ('class_no_room', c.id)
                    if key not in seen:
                        seen.add(key)
                        warnings.append(('class_no_room', f'Класс {c.name} не имеет прикреплённого кабинета', c))

        # Предметы с requires_fixed_classroom без default_classroom
        for s in Subject.query.filter_by(requires_fixed_classroom=True).filter(
                Subject.default_classroom_id.is_(None)).all():
            if any(not a.preferred_classroom_id for a in s.assignments):
                key = ('fixed_subject_default', s.id)
                if key not in seen:
                    seen.add(key)
                    warnings.append(('fixed_subject_default',
                        f'Предмет "{s.name}" требует кабинет, но не указан кабинет по умолчанию', s))

        return warnings
