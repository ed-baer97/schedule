"""Tests for services: validators and auto_scheduler."""
import pytest
from app.models import (
    Teacher, Classroom, SchoolClass, Shift, Subject,
    TeachingAssignment, ScheduleCell, ScheduleSettings
)
from app.services.validators import ScheduleValidator
from app.services.auto_scheduler import AutoScheduler


class TestScheduleValidator:
    def test_no_conflict_on_empty_schedule(self, sample_data, db):
        v = ScheduleValidator()
        a = sample_data['assignments'][0]
        errors = v.validate_cell(assignment=a, day=1, lesson=1)
        assert errors == []

    def test_teacher_conflict(self, sample_data, db):
        v = ScheduleValidator()
        a1 = sample_data['assignments'][0]
        a2 = sample_data['assignments'][2]
        cell = ScheduleCell(
            class_id=a1.class_id, day_of_week=1, lesson_number=1,
            assignment_id=a1.id
        )
        db.session.add(cell)
        db.session.commit()

        errors = v.validate_cell(assignment=a2, day=1, lesson=1)
        assert len(errors) > 0
        assert any('занят' in e for e in errors)

    def test_classroom_conflict(self, sample_data, db):
        v = ScheduleValidator()
        a1 = sample_data['assignments'][0]
        classroom = sample_data['classrooms'][0]
        cell = ScheduleCell(
            class_id=a1.class_id, day_of_week=1, lesson_number=1,
            assignment_id=a1.id, classroom_id=classroom.id
        )
        db.session.add(cell)
        db.session.commit()

        a2 = sample_data['assignments'][1]
        errors = v.validate_cell(assignment=a2, day=1, lesson=1, classroom_id=classroom.id)
        assert any('Кабинет' in e for e in errors)

    def test_classroom_multi_capacity_no_conflict(self, sample_data, db):
        v = ScheduleValidator()
        gym = sample_data['classrooms'][2]
        a1 = sample_data['assignments'][0]
        cell = ScheduleCell(
            class_id=a1.class_id, day_of_week=1, lesson_number=1,
            assignment_id=a1.id, classroom_id=gym.id
        )
        db.session.add(cell)
        db.session.commit()

        conflict = v.check_classroom_conflict(gym.id, 1, 1)
        assert conflict is False

    def test_classroom_multi_capacity_conflict_when_full(self, sample_data, db):
        v = ScheduleValidator()
        gym = sample_data['classrooms'][2]
        a1 = sample_data['assignments'][0]
        a2 = sample_data['assignments'][1]
        cell1 = ScheduleCell(
            class_id=a1.class_id, day_of_week=1, lesson_number=1,
            assignment_id=a1.id, classroom_id=gym.id
        )
        cell2 = ScheduleCell(
            class_id=a2.class_id, day_of_week=1, lesson_number=1,
            assignment_id=a2.id, classroom_id=gym.id
        )
        db.session.add_all([cell1, cell2])
        db.session.commit()

        conflict = v.check_classroom_conflict(gym.id, 1, 1)
        assert conflict is True

    def test_class_conflict(self, sample_data, db):
        v = ScheduleValidator()
        a1 = sample_data['assignments'][0]
        a2 = sample_data['assignments'][1]
        cell = ScheduleCell(
            class_id=a1.class_id, day_of_week=1, lesson_number=1,
            assignment_id=a1.id
        )
        db.session.add(cell)
        db.session.commit()

        conflict = v.check_class_conflict(a2.class_id, 1, 1)
        assert conflict is True

    def test_group_no_conflict_different_groups(self, sample_data, db):
        v = ScheduleValidator()
        s = sample_data['subjects'][0]
        sc = sample_data['classes'][0]
        t1 = sample_data['teachers'][0]
        t2 = sample_data['teachers'][1]

        a_grp1 = TeachingAssignment(
            subject_id=s.id, teacher_id=t1.id,
            class_id=sc.id, hours_per_week=2, group_number=1
        )
        a_grp2 = TeachingAssignment(
            subject_id=s.id, teacher_id=t2.id,
            class_id=sc.id, hours_per_week=2, group_number=2
        )
        db.session.add_all([a_grp1, a_grp2])
        db.session.flush()

        cell = ScheduleCell(
            class_id=sc.id, day_of_week=3, lesson_number=2,
            assignment_id=a_grp1.id
        )
        db.session.add(cell)
        db.session.commit()

        conflict = v.check_class_conflict(sc.id, 3, 2, group_number=2)
        assert conflict is False

    def test_group_conflict_same_group(self, sample_data, db):
        v = ScheduleValidator()
        s = sample_data['subjects'][0]
        sc = sample_data['classes'][0]
        t1 = sample_data['teachers'][0]

        a_grp1 = TeachingAssignment(
            subject_id=s.id, teacher_id=t1.id,
            class_id=sc.id, hours_per_week=2, group_number=1
        )
        db.session.add(a_grp1)
        db.session.flush()

        cell = ScheduleCell(
            class_id=sc.id, day_of_week=3, lesson_number=2,
            assignment_id=a_grp1.id
        )
        db.session.add(cell)
        db.session.commit()

        conflict = v.check_class_conflict(sc.id, 3, 2, group_number=1)
        assert conflict is True

    def test_subject_per_day_limit(self, sample_data, db):
        v = ScheduleValidator()
        a = sample_data['assignments'][0]
        for lesson in range(1, 3):
            cell = ScheduleCell(
                class_id=a.class_id, day_of_week=1, lesson_number=lesson,
                assignment_id=a.id
            )
            db.session.add(cell)
        db.session.commit()

        exceeded = v.check_subject_per_day_limit(a, 1)
        assert exceeded is True

    def test_subject_per_day_not_exceeded(self, sample_data, db):
        v = ScheduleValidator()
        a = sample_data['assignments'][0]
        cell = ScheduleCell(
            class_id=a.class_id, day_of_week=1, lesson_number=1,
            assignment_id=a.id
        )
        db.session.add(cell)
        db.session.commit()

        exceeded = v.check_subject_per_day_limit(a, 1)
        assert exceeded is False

    def test_exclude_cell_id(self, sample_data, db):
        v = ScheduleValidator()
        a = sample_data['assignments'][0]
        cell = ScheduleCell(
            class_id=a.class_id, day_of_week=1, lesson_number=1,
            assignment_id=a.id
        )
        db.session.add(cell)
        db.session.commit()

        conflict = v.check_teacher_conflict(a.teacher_id, 1, 1, exclude_cell_id=cell.id)
        assert conflict is False

    def test_get_teacher_windows(self, sample_data, db):
        v = ScheduleValidator()
        a = sample_data['assignments'][0]
        for lesson in [1, 3]:
            cell = ScheduleCell(
                class_id=a.class_id, day_of_week=1, lesson_number=lesson,
                assignment_id=a.id
            )
            db.session.add(cell)
        db.session.commit()

        windows = v.get_teacher_windows(a.teacher_id, working_days=5)
        assert (1, 2) in windows

    def test_no_windows_for_consecutive_lessons(self, sample_data, db):
        v = ScheduleValidator()
        a = sample_data['assignments'][0]
        for lesson in [1, 2, 3]:
            cell = ScheduleCell(
                class_id=a.class_id, day_of_week=1, lesson_number=lesson,
                assignment_id=a.id
            )
            db.session.add(cell)
        db.session.commit()

        windows = v.get_teacher_windows(a.teacher_id, working_days=5)
        day1_windows = [w for w in windows if w[0] == 1]
        assert len(day1_windows) == 0

    def test_check_classroom_conflict_none_id(self, sample_data, db):
        v = ScheduleValidator()
        assert v.check_classroom_conflict(None, 1, 1) is False


class TestAutoScheduler:
    def test_schedule_by_teacher_ladder(self, sample_data, db):
        scheduler = AutoScheduler()
        teacher = sample_data['teachers'][0]
        count = scheduler.schedule_by_teacher_ladder(teacher.id, 'elementary')
        assert count > 0
        cells = ScheduleCell.query.join(TeachingAssignment).filter(
            TeachingAssignment.teacher_id == teacher.id
        ).all()
        assert len(cells) > 0

    def test_schedule_class_day(self, sample_data, db):
        scheduler = AutoScheduler()
        sc = sample_data['classes'][0]
        count = scheduler.schedule_class_day(sc.id, 1, 'elementary')
        assert count > 0

    def test_auto_schedule_all(self, sample_data, db):
        scheduler = AutoScheduler()
        count = scheduler.auto_schedule_all('elementary')
        assert count > 0
        total = ScheduleCell.query.join(SchoolClass).filter(
            SchoolClass.school_level == 'elementary'
        ).count()
        assert total > 0

    def test_clear_schedule_by_level(self, sample_data, db):
        scheduler = AutoScheduler()
        scheduler.auto_schedule_all('elementary')
        before = ScheduleCell.query.join(SchoolClass).filter(
            SchoolClass.school_level == 'elementary'
        ).count()
        assert before > 0

        count = scheduler.clear_schedule(school_level='elementary')
        assert count == before
        after = ScheduleCell.query.join(SchoolClass).filter(
            SchoolClass.school_level == 'elementary'
        ).count()
        assert after == 0

    def test_clear_schedule_by_class(self, sample_data, db):
        scheduler = AutoScheduler()
        sc = sample_data['classes'][0]
        scheduler.schedule_class_day(sc.id, 1, 'elementary')
        count = scheduler.clear_schedule(class_id=sc.id)
        assert count > 0

    def test_clear_schedule_by_teacher(self, sample_data, db):
        scheduler = AutoScheduler()
        teacher = sample_data['teachers'][0]
        scheduler.schedule_by_teacher_ladder(teacher.id, 'elementary')
        count = scheduler.clear_schedule(teacher_id=teacher.id)
        assert count > 0

    def test_no_double_booking_after_auto_schedule(self, sample_data, db):
        """After auto scheduling, no teacher should be double-booked."""
        scheduler = AutoScheduler()
        scheduler.auto_schedule_all('elementary')

        cells = ScheduleCell.query.all()
        seen_teacher_slots = {}
        for cell in cells:
            tid = cell.assignment.teacher_id
            if tid is None:
                continue
            key = (tid, cell.day_of_week, cell.lesson_number)
            if key in seen_teacher_slots:
                pytest.fail(f'Teacher {tid} double-booked at day={cell.day_of_week} lesson={cell.lesson_number}')
            seen_teacher_slots[key] = cell.id

    def test_get_classroom_for_cell_fixed_subject(self, sample_data, db):
        scheduler = AutoScheduler()
        pe_subject = sample_data['subjects'][2]
        sc = sample_data['classes'][0]
        gym = sample_data['classrooms'][2]

        a = TeachingAssignment(
            subject_id=pe_subject.id, teacher_id=sample_data['teachers'][0].id,
            class_id=sc.id, hours_per_week=2
        )
        db.session.add(a)
        db.session.commit()

        cid = scheduler._get_classroom_for_cell(a, 'elementary')
        assert cid == gym.id

    def test_get_classroom_for_cell_teacher_room_mode(self, sample_data, db):
        scheduler = AutoScheduler()
        settings = sample_data['settings'][0]
        settings.classroom_mode = 'teacher_room'
        db.session.commit()

        a = sample_data['assignments'][0]
        cid = scheduler._get_classroom_for_cell(a, 'elementary')
        assert cid == a.teacher.home_classroom_id

    def test_get_classroom_for_cell_class_room_mode(self, sample_data, db):
        scheduler = AutoScheduler()
        settings = sample_data['settings'][0]
        settings.classroom_mode = 'class_room'
        db.session.commit()

        a = sample_data['assignments'][0]
        cid = scheduler._get_classroom_for_cell(a, 'elementary')
        assert cid == a.school_class.home_classroom_id

    def test_complementary_subgroup_scheduling(self, sample_data, db):
        """When a subgroup is placed, the complementary subgroup should be placed too."""
        scheduler = AutoScheduler()
        s = sample_data['subjects'][0]
        sc = sample_data['classes'][0]
        t1 = sample_data['teachers'][0]
        t2 = sample_data['teachers'][1]

        a_grp1 = TeachingAssignment(
            subject_id=s.id, teacher_id=t1.id,
            class_id=sc.id, hours_per_week=2, group_number=1
        )
        a_grp2 = TeachingAssignment(
            subject_id=s.id, teacher_id=t2.id,
            class_id=sc.id, hours_per_week=2, group_number=2
        )
        db.session.add_all([a_grp1, a_grp2])
        db.session.commit()

        count = scheduler.schedule_by_teacher_ladder(t1.id, 'elementary')
        cells_grp2 = ScheduleCell.query.filter_by(assignment_id=a_grp2.id).count()
        assert cells_grp2 > 0

    def test_get_classroom_warnings(self, sample_data, db):
        scheduler = AutoScheduler()
        warnings = scheduler.get_classroom_warnings('elementary')
        assert isinstance(warnings, list)

    def test_get_classroom_warnings_missing_classroom(self, sample_data, db):
        """Classes without home_classroom should generate warnings in class_room mode."""
        sc = SchoolClass(name='2Б', grade=2, school_level='elementary',
                         shift_id=sample_data['shifts'][0].id)
        db.session.add(sc)
        db.session.flush()
        s = sample_data['subjects'][0]
        a = TeachingAssignment(
            subject_id=s.id, teacher_id=sample_data['teachers'][0].id,
            class_id=sc.id, hours_per_week=2
        )
        db.session.add(a)
        db.session.commit()

        scheduler = AutoScheduler()
        warnings = scheduler.get_classroom_warnings('elementary')
        class_warnings = [w for w in warnings if w[0] == 'class_no_room' and '2Б' in w[1]]
        assert len(class_warnings) > 0
