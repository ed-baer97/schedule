"""Tests for database models."""
import pytest
from app.models import (
    Teacher, Classroom, SchoolClass, Shift, Subject,
    TeachingAssignment, ScheduleCell, ScheduleSettings
)


class TestTeacherModel:
    def test_create_teacher(self, db):
        t = Teacher(full_name='Тестов Тест Тестович', email='test@test.ru', phone='+79001234567')
        db.session.add(t)
        db.session.commit()
        assert t.id is not None
        assert t.full_name == 'Тестов Тест Тестович'

    def test_teacher_repr(self, db):
        t = Teacher(full_name='Иванов И.И.')
        db.session.add(t)
        db.session.commit()
        assert repr(t) == '<Teacher Иванов И.И.>'

    def test_teacher_display_name(self, db):
        t = Teacher(full_name='Иванов Иван Иванович')
        assert t.display_name == 'Иванов Иван Иванович'

    def test_teacher_home_classroom_relationship(self, db):
        c = Classroom(number='100', name='Каб. 100')
        db.session.add(c)
        db.session.flush()
        t = Teacher(full_name='Учитель', home_classroom_id=c.id)
        db.session.add(t)
        db.session.commit()
        assert t.home_classroom.number == '100'


class TestClassroomModel:
    def test_create_classroom(self, db):
        c = Classroom(number='201', name='Физика', floor=2, capacity=30)
        db.session.add(c)
        db.session.commit()
        assert c.id is not None

    def test_classroom_display_name_with_name(self, db):
        c = Classroom(number='201', name='Физика')
        assert c.display_name == '201 (Физика)'

    def test_classroom_display_name_without_name(self, db):
        c = Classroom(number='201')
        assert c.display_name == '201'

    def test_classroom_classes_capacity_default(self, db):
        c = Classroom(number='202')
        db.session.add(c)
        db.session.commit()
        assert c.classes_capacity == 1

    def test_classroom_repr(self, db):
        c = Classroom(number='303')
        db.session.add(c)
        db.session.commit()
        assert repr(c) == '<Classroom 303>'


class TestShiftModel:
    def test_create_shift(self, db):
        s = Shift(name='1 смена', school_level='elementary', start_lesson=1, lessons_count=5)
        db.session.add(s)
        db.session.commit()
        assert s.id is not None

    def test_shift_school_level_display_elementary(self, db):
        s = Shift(name='1 смена', school_level='elementary')
        assert s.school_level_display == 'Начальная школа'

    def test_shift_school_level_display_secondary(self, db):
        s = Shift(name='1 смена', school_level='secondary')
        assert s.school_level_display == 'Основная школа'


class TestSchoolClassModel:
    def test_create_school_class(self, db):
        s = Shift(name='1 смена', school_level='elementary')
        db.session.add(s)
        db.session.flush()
        sc = SchoolClass(name='3А', grade=3, school_level='elementary', shift_id=s.id)
        db.session.add(sc)
        db.session.commit()
        assert sc.id is not None

    def test_school_class_school_level_display(self, db):
        sc = SchoolClass(name='1А', grade=1, school_level='elementary')
        assert sc.school_level_display == 'Начальная школа'
        sc2 = SchoolClass(name='5Б', grade=5, school_level='secondary')
        assert sc2.school_level_display == 'Основная школа'

    def test_school_class_repr(self, db):
        sc = SchoolClass(name='2Б', grade=2, school_level='elementary')
        db.session.add(sc)
        db.session.commit()
        assert repr(sc) == '<SchoolClass 2Б>'


class TestSubjectModel:
    def test_create_subject(self, db):
        s = Subject(name='Физика', color='#9b59b6')
        db.session.add(s)
        db.session.commit()
        assert s.id is not None
        assert s.requires_fixed_classroom is False

    def test_subject_with_fixed_classroom(self, db):
        c = Classroom(number='СЗ', name='Спортзал')
        db.session.add(c)
        db.session.flush()
        s = Subject(name='Физкультура', requires_fixed_classroom=True, default_classroom_id=c.id)
        db.session.add(s)
        db.session.commit()
        assert s.requires_fixed_classroom is True
        assert s.default_classroom.number == 'СЗ'

    def test_subject_display_name(self, db):
        s = Subject(name='Алгебра')
        assert s.display_name == 'Алгебра'


class TestTeachingAssignmentModel:
    def test_create_assignment(self, sample_data):
        a = sample_data['assignments'][0]
        assert a.id is not None
        assert a.hours_per_week == 4

    def test_assignment_is_group_subject(self, db):
        s = Subject(name='Тест')
        db.session.add(s)
        sc = SchoolClass(name='1А', grade=1, school_level='elementary')
        db.session.add(sc)
        db.session.flush()
        a = TeachingAssignment(subject_id=s.id, class_id=sc.id, hours_per_week=2, group_number=1)
        assert a.is_group_subject is True
        a2 = TeachingAssignment(subject_id=s.id, class_id=sc.id, hours_per_week=2, group_number=None)
        assert a2.is_group_subject is False

    def test_assignment_scheduled_and_remaining_hours(self, sample_data, db):
        a = sample_data['assignments'][0]
        assert a.scheduled_hours == 0
        assert a.remaining_hours == 4

        cell = ScheduleCell(
            class_id=a.class_id, day_of_week=1, lesson_number=1,
            assignment_id=a.id
        )
        db.session.add(cell)
        db.session.commit()
        assert a.scheduled_hours == 1
        assert a.remaining_hours == 3

    def test_assignment_display_name(self, sample_data):
        a = sample_data['assignments'][0]
        assert a.display_name == 'Математика'

    def test_assignment_display_name_with_group(self, db):
        s = Subject(name='Англ. язык')
        sc = SchoolClass(name='5А', grade=5, school_level='secondary')
        db.session.add_all([s, sc])
        db.session.flush()
        a = TeachingAssignment(subject_id=s.id, class_id=sc.id, hours_per_week=3, group_number=1)
        db.session.add(a)
        db.session.commit()
        assert a.display_name == 'Англ. язык (гр.1)'


class TestScheduleCellModel:
    def test_create_schedule_cell(self, sample_data, db):
        a = sample_data['assignments'][0]
        cell = ScheduleCell(
            class_id=a.class_id, day_of_week=1, lesson_number=1,
            assignment_id=a.id, classroom_id=sample_data['classrooms'][0].id
        )
        db.session.add(cell)
        db.session.commit()
        assert cell.id is not None
        assert cell.subject.name == 'Математика'
        assert cell.teacher.full_name == 'Иванов Иван Иванович'


class TestScheduleSettingsModel:
    def test_create_settings(self, db):
        s = ScheduleSettings(
            school_level='elementary', working_days=5,
            max_lessons_per_day=5, max_lessons_per_subject_per_day=1
        )
        db.session.add(s)
        db.session.commit()
        assert s.id is not None
        assert s.classroom_mode == 'class_room'
