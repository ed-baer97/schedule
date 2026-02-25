import os
import pytest
from app import create_app, db as _db
from app.config import TestingConfig


@pytest.fixture(scope='session')
def app():
    """Create application for testing."""
    os.environ['DATABASE_URL'] = 'sqlite://'
    app = create_app(TestingConfig)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SERVER_NAME'] = 'localhost'
    return app


@pytest.fixture(scope='function')
def db(app):
    """Create a fresh database for each test."""
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.rollback()
        _db.drop_all()


@pytest.fixture(scope='function')
def client(app, db):
    """Flask test client with a clean database."""
    with app.test_client() as client:
        with app.app_context():
            yield client


@pytest.fixture
def sample_data(db):
    """Create a standard set of sample data for tests."""
    from app.models import (
        Teacher, Classroom, Shift, SchoolClass, Subject,
        TeachingAssignment, ScheduleSettings
    )

    classroom1 = Classroom(number='101', name='Математика', floor=1, capacity=30, classes_capacity=1)
    classroom2 = Classroom(number='102', name='Русский язык', floor=1, capacity=30, classes_capacity=1)
    classroom3 = Classroom(number='СЗ', name='Спортзал', floor=1, capacity=60, classes_capacity=2)
    db.session.add_all([classroom1, classroom2, classroom3])
    db.session.flush()

    teacher1 = Teacher(full_name='Иванов Иван Иванович', email='ivanov@school.ru', home_classroom_id=classroom1.id)
    teacher2 = Teacher(full_name='Петрова Мария Сергеевна', email='petrova@school.ru', home_classroom_id=classroom2.id)
    db.session.add_all([teacher1, teacher2])
    db.session.flush()

    shift1 = Shift(name='1 смена', school_level='elementary', start_lesson=1, lessons_count=5)
    shift2 = Shift(name='1 смена', school_level='secondary', start_lesson=1, lessons_count=7)
    db.session.add_all([shift1, shift2])
    db.session.flush()

    class1 = SchoolClass(name='1А', grade=1, school_level='elementary', shift_id=shift1.id, home_classroom_id=classroom1.id)
    class2 = SchoolClass(name='5Б', grade=5, school_level='secondary', shift_id=shift2.id, home_classroom_id=classroom2.id)
    db.session.add_all([class1, class2])
    db.session.flush()

    subject1 = Subject(name='Математика', color='#e74c3c')
    subject2 = Subject(name='Русский язык', color='#3498db')
    subject3 = Subject(name='Физкультура', color='#2ecc71', requires_fixed_classroom=True, default_classroom_id=classroom3.id)
    db.session.add_all([subject1, subject2, subject3])
    db.session.flush()

    assignment1 = TeachingAssignment(
        subject_id=subject1.id, teacher_id=teacher1.id,
        class_id=class1.id, hours_per_week=4
    )
    assignment2 = TeachingAssignment(
        subject_id=subject2.id, teacher_id=teacher2.id,
        class_id=class1.id, hours_per_week=5
    )
    assignment3 = TeachingAssignment(
        subject_id=subject1.id, teacher_id=teacher1.id,
        class_id=class2.id, hours_per_week=5
    )
    db.session.add_all([assignment1, assignment2, assignment3])
    db.session.flush()

    settings_elem = ScheduleSettings(
        school_level='elementary', working_days=5,
        max_lessons_per_day=5, max_lessons_per_subject_per_day=2
    )
    settings_sec = ScheduleSettings(
        school_level='secondary', working_days=5,
        max_lessons_per_day=7, max_lessons_per_subject_per_day=2
    )
    db.session.add_all([settings_elem, settings_sec])
    db.session.commit()

    return {
        'classrooms': [classroom1, classroom2, classroom3],
        'teachers': [teacher1, teacher2],
        'shifts': [shift1, shift2],
        'classes': [class1, class2],
        'subjects': [subject1, subject2, subject3],
        'assignments': [assignment1, assignment2, assignment3],
        'settings': [settings_elem, settings_sec],
    }
