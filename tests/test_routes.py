"""Tests for all route blueprints."""
import pytest


class TestMainRoutes:
    def test_index_page(self, client, sample_data):
        resp = client.get('/')
        assert resp.status_code == 200
        assert 'Иванов'.encode() in resp.data or resp.status_code == 200


class TestTeacherRoutes:
    def test_list_teachers(self, client, sample_data):
        resp = client.get('/teachers/')
        assert resp.status_code == 200

    def test_create_teacher_get(self, client, db):
        resp = client.get('/teachers/create')
        assert resp.status_code == 200

    def test_create_teacher_post(self, client, db):
        resp = client.post('/teachers/create', data={
            'full_name': 'Новый Учитель',
            'email': 'new@school.ru',
            'phone': '+79001112233',
        }, follow_redirects=True)
        assert resp.status_code == 200
        from app.models import Teacher
        t = Teacher.query.filter_by(full_name='Новый Учитель').first()
        assert t is not None

    def test_edit_teacher(self, client, sample_data):
        teacher = sample_data['teachers'][0]
        resp = client.get(f'/teachers/{teacher.id}/edit')
        assert resp.status_code == 200

        resp = client.post(f'/teachers/{teacher.id}/edit', data={
            'full_name': 'Обновлённый Учитель',
            'email': 'updated@school.ru',
            'phone': '',
        }, follow_redirects=True)
        assert resp.status_code == 200

    def test_delete_teacher(self, client, sample_data, db):
        from app.models import Teacher
        t = Teacher(full_name='Удаляемый Учитель')
        db.session.add(t)
        db.session.commit()
        resp = client.post(f'/teachers/{t.id}/delete', follow_redirects=True)
        assert resp.status_code == 200
        assert Teacher.query.get(t.id) is None

    def test_edit_nonexistent_teacher(self, client, db):
        resp = client.get('/teachers/99999/edit')
        assert resp.status_code == 404


class TestClassroomRoutes:
    def test_list_classrooms(self, client, sample_data):
        resp = client.get('/classrooms/')
        assert resp.status_code == 200

    def test_create_classroom_get(self, client, db):
        resp = client.get('/classrooms/create')
        assert resp.status_code == 200

    def test_create_classroom_post(self, client, db):
        resp = client.post('/classrooms/create', data={
            'number': '301',
            'name': 'Химия',
            'floor': '3',
            'building': 'Корпус 1',
            'classes_capacity': '1',
        }, follow_redirects=True)
        assert resp.status_code == 200
        from app.models import Classroom
        c = Classroom.query.filter_by(number='301').first()
        assert c is not None
        assert c.name == 'Химия'

    def test_edit_classroom(self, client, sample_data):
        classroom = sample_data['classrooms'][0]
        resp = client.post(f'/classrooms/{classroom.id}/edit', data={
            'number': '101A',
            'name': 'Обновлённый',
            'floor': '2',
            'building': '',
            'classes_capacity': '1',
        }, follow_redirects=True)
        assert resp.status_code == 200

    def test_delete_classroom(self, client, db):
        from app.models import Classroom
        c = Classroom(number='999')
        db.session.add(c)
        db.session.commit()
        resp = client.post(f'/classrooms/{c.id}/delete', follow_redirects=True)
        assert resp.status_code == 200
        assert Classroom.query.get(c.id) is None


class TestShiftRoutes:
    def test_list_shifts(self, client, sample_data):
        resp = client.get('/shifts/')
        assert resp.status_code == 200

    def test_create_shift_get(self, client, db):
        resp = client.get('/shifts/create')
        assert resp.status_code == 200

    def test_create_shift_post(self, client, db):
        resp = client.post('/shifts/create', data={
            'name': '2 смена',
            'school_level': 'secondary',
            'start_lesson': '6',
            'lessons_count': '5',
        }, follow_redirects=True)
        assert resp.status_code == 200
        from app.models import Shift
        s = Shift.query.filter_by(name='2 смена').first()
        assert s is not None
        assert s.start_lesson == 6

    def test_edit_shift(self, client, sample_data):
        shift = sample_data['shifts'][0]
        resp = client.post(f'/shifts/{shift.id}/edit', data={
            'name': '1 смена (обновл.)',
            'school_level': 'elementary',
            'start_lesson': '1',
            'lessons_count': '6',
        }, follow_redirects=True)
        assert resp.status_code == 200

    def test_delete_shift(self, client, db):
        from app.models import Shift
        s = Shift(name='Удаляемая', school_level='elementary')
        db.session.add(s)
        db.session.commit()
        resp = client.post(f'/shifts/{s.id}/delete', follow_redirects=True)
        assert resp.status_code == 200
        assert Shift.query.get(s.id) is None


class TestClassRoutes:
    def test_list_classes(self, client, sample_data):
        resp = client.get('/classes/')
        assert resp.status_code == 200

    def test_create_class_get(self, client, sample_data):
        resp = client.get('/classes/create')
        assert resp.status_code == 200

    def test_create_class_post(self, client, sample_data):
        shift = sample_data['shifts'][0]
        resp = client.post('/classes/create', data={
            'name': '2А',
            'school_level': 'elementary',
            'shift_id': str(shift.id),
        }, follow_redirects=True)
        assert resp.status_code == 200
        from app.models import SchoolClass
        sc = SchoolClass.query.filter_by(name='2А').first()
        assert sc is not None
        assert sc.grade == 2

    def test_create_class_grade_extraction(self, client, sample_data):
        resp = client.post('/classes/create', data={
            'name': '10Б',
            'school_level': 'secondary',
        }, follow_redirects=True)
        assert resp.status_code == 200
        from app.models import SchoolClass
        sc = SchoolClass.query.filter_by(name='10Б').first()
        assert sc is not None
        assert sc.grade == 10

    def test_edit_class(self, client, sample_data):
        sc = sample_data['classes'][0]
        resp = client.post(f'/classes/{sc.id}/edit', data={
            'name': '1Б',
            'school_level': 'elementary',
        }, follow_redirects=True)
        assert resp.status_code == 200

    def test_delete_class(self, client, db):
        from app.models import SchoolClass
        sc = SchoolClass(name='9В', grade=9, school_level='secondary')
        db.session.add(sc)
        db.session.commit()
        resp = client.post(f'/classes/{sc.id}/delete', follow_redirects=True)
        assert resp.status_code == 200
        assert SchoolClass.query.get(sc.id) is None

    def test_batch_update_shift(self, client, sample_data):
        sc = sample_data['classes'][0]
        shift = sample_data['shifts'][0]
        resp = client.post('/classes/batch-shift', data={
            'class_ids': [str(sc.id)],
            'shift_id': str(shift.id),
        }, follow_redirects=True)
        assert resp.status_code == 200

    def test_batch_update_shift_empty(self, client, sample_data):
        resp = client.post('/classes/batch-shift', data={
            'shift_id': str(sample_data['shifts'][0].id),
        }, follow_redirects=True)
        assert resp.status_code == 200


class TestSubjectRoutes:
    def test_list_subjects_no_level(self, client, sample_data):
        resp = client.get('/subjects/')
        assert resp.status_code == 200

    def test_list_subjects_elementary(self, client, sample_data):
        resp = client.get('/subjects/?school_level=elementary')
        assert resp.status_code == 200

    def test_list_subjects_invalid_level_redirects(self, client, sample_data):
        resp = client.get('/subjects/?school_level=invalid')
        assert resp.status_code == 302

    def test_create_subject_get(self, client, db):
        resp = client.get('/subjects/create')
        assert resp.status_code == 200

    def test_create_subject_post(self, client, db):
        resp = client.post('/subjects/create', data={
            'name': 'Биология',
        }, follow_redirects=True)
        assert resp.status_code == 200
        from app.models import Subject
        s = Subject.query.filter_by(name='Биология').first()
        assert s is not None

    def test_edit_subject(self, client, sample_data):
        s = sample_data['subjects'][0]
        resp = client.post(f'/subjects/{s.id}/edit', data={
            'name': 'Алгебра',
        }, follow_redirects=True)
        assert resp.status_code == 200

    def test_delete_subject(self, client, db):
        from app.models import Subject
        s = Subject(name='Удаляемый')
        db.session.add(s)
        db.session.commit()
        resp = client.post(f'/subjects/{s.id}/delete', follow_redirects=True)
        assert resp.status_code == 200
        assert Subject.query.get(s.id) is None

    def test_subject_assignments_page(self, client, sample_data):
        s = sample_data['subjects'][0]
        resp = client.get(f'/subjects/{s.id}/assignments?school_level=elementary')
        assert resp.status_code == 200


class TestAssignmentRoutes:
    def test_list_assignments(self, client, sample_data):
        resp = client.get('/assignments/?school_level=elementary')
        assert resp.status_code == 200

    def test_create_assignment_get(self, client, sample_data):
        resp = client.get('/assignments/create')
        assert resp.status_code == 200

    def test_create_assignment_post(self, client, sample_data):
        s = sample_data['subjects'][0]
        t = sample_data['teachers'][0]
        c = sample_data['classes'][0]
        resp = client.post('/assignments/create', data={
            'subject_id': str(s.id),
            'teacher_id': str(t.id),
            'class_id': str(c.id),
            'hours_per_week': '3',
        }, follow_redirects=True)
        assert resp.status_code == 200

    def test_edit_assignment(self, client, sample_data):
        a = sample_data['assignments'][0]
        resp = client.post(f'/assignments/{a.id}/edit', data={
            'subject_id': str(a.subject_id),
            'teacher_id': str(a.teacher_id),
            'class_id': str(a.class_id),
            'hours_per_week': '6',
        }, follow_redirects=True)
        assert resp.status_code == 200

    def test_assign_teacher(self, client, sample_data, db):
        from app.models import TeachingAssignment
        a = sample_data['assignments'][0]
        new_teacher = sample_data['teachers'][1]
        resp = client.post(f'/assignments/{a.id}/assign-teacher', data={
            'teacher_id': str(new_teacher.id),
        }, follow_redirects=True)
        assert resp.status_code == 200

    def test_delete_assignment(self, client, sample_data, db):
        from app.models import TeachingAssignment, Subject, SchoolClass
        s = Subject(name='Удаляемый предмет')
        sc = SchoolClass(name='4Г', grade=4, school_level='elementary')
        db.session.add_all([s, sc])
        db.session.flush()
        a = TeachingAssignment(subject_id=s.id, class_id=sc.id, hours_per_week=1)
        db.session.add(a)
        db.session.commit()
        resp = client.post(f'/assignments/{a.id}/delete', follow_redirects=True)
        assert resp.status_code == 200
        assert TeachingAssignment.query.get(a.id) is None


class TestWorkloadRoutes:
    def test_workload_page(self, client, sample_data):
        resp = client.get('/workload/?school_level=elementary')
        assert resp.status_code == 200

    def test_workload_update_create(self, client, sample_data):
        c = sample_data['classes'][0]
        s = sample_data['subjects'][1]
        resp = client.post('/workload/update', data={
            'class_id': str(c.id),
            'subject_id': str(s.id),
            'hours': '3',
        }, follow_redirects=True)
        assert resp.status_code == 200

    def test_workload_update_ajax(self, client, sample_data):
        c = sample_data['classes'][0]
        s = sample_data['subjects'][0]
        from app.models import TeachingAssignment
        existing = TeachingAssignment.query.filter_by(
            class_id=c.id, subject_id=s.id, teacher_id=None
        ).first()
        if existing:
            from app import db as _db
            _db.session.delete(existing)
            _db.session.commit()
        resp = client.post('/workload/update', data={
            'class_id': str(c.id),
            'subject_id': str(s.id),
            'hours': '5',
        }, headers={'X-Requested-With': 'XMLHttpRequest'})
        assert resp.status_code == 200
        assert resp.json['status'] == 'ok'

    def test_workload_update_zero_removes(self, client, sample_data, db):
        from app.models import TeachingAssignment, Subject, SchoolClass
        s = Subject(name='Удаляемый2')
        sc = SchoolClass(name='3Д', grade=3, school_level='elementary')
        db.session.add_all([s, sc])
        db.session.flush()
        a = TeachingAssignment(subject_id=s.id, class_id=sc.id, hours_per_week=2, teacher_id=None)
        db.session.add(a)
        db.session.commit()
        resp = client.post('/workload/update', data={
            'class_id': str(sc.id),
            'subject_id': str(s.id),
            'hours': '0',
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert TeachingAssignment.query.get(a.id) is None


class TestScheduleRoutes:
    def test_schedule_index(self, client, sample_data):
        resp = client.get('/schedule/?school_level=elementary')
        assert resp.status_code == 200

    def test_schedule_settings_get(self, client, sample_data):
        resp = client.get('/schedule/settings')
        assert resp.status_code == 200

    def test_schedule_settings_post(self, client, sample_data):
        resp = client.post('/schedule/settings', data={
            'school_level': 'elementary',
            'working_days': '6',
            'max_lessons_per_day': '6',
            'max_lessons_per_subject_per_day': '2',
            'classroom_mode': 'class_room',
        }, follow_redirects=True)
        assert resp.status_code == 200

    def test_add_cell(self, client, sample_data):
        a = sample_data['assignments'][0]
        c = sample_data['classrooms'][0]
        resp = client.post('/schedule/add-cell', data={
            'class_id': str(a.class_id),
            'day': '1',
            'lesson': '1',
            'assignment_id': str(a.id),
            'classroom_id': str(c.id),
        }, follow_redirects=True)
        assert resp.status_code == 200

    def test_add_cell_ajax(self, client, sample_data):
        a = sample_data['assignments'][0]
        resp = client.post('/schedule/add-cell', data={
            'class_id': str(a.class_id),
            'day': '1',
            'lesson': '1',
            'assignment_id': str(a.id),
        }, headers={'X-Requested-With': 'XMLHttpRequest'})
        assert resp.status_code == 200
        assert resp.json['status'] == 'ok'

    def test_add_cell_teacher_conflict(self, client, sample_data, db):
        from app.models import ScheduleCell
        a = sample_data['assignments'][0]
        cell = ScheduleCell(
            class_id=a.class_id, day_of_week=1, lesson_number=1,
            assignment_id=a.id
        )
        db.session.add(cell)
        db.session.commit()

        a2 = sample_data['assignments'][2]
        resp = client.post('/schedule/add-cell', data={
            'class_id': str(a2.class_id),
            'day': '1',
            'lesson': '1',
            'assignment_id': str(a2.id),
        }, headers={'X-Requested-With': 'XMLHttpRequest'})
        assert resp.status_code == 400

    def test_remove_cell(self, client, sample_data, db):
        from app.models import ScheduleCell
        a = sample_data['assignments'][0]
        cell = ScheduleCell(
            class_id=a.class_id, day_of_week=2, lesson_number=2,
            assignment_id=a.id
        )
        db.session.add(cell)
        db.session.commit()
        resp = client.post(f'/schedule/remove-cell/{cell.id}', follow_redirects=True)
        assert resp.status_code == 200
        assert ScheduleCell.query.get(cell.id) is None

    def test_move_cell(self, client, sample_data, db):
        from app.models import ScheduleCell
        a = sample_data['assignments'][0]
        cell = ScheduleCell(
            class_id=a.class_id, day_of_week=1, lesson_number=1,
            assignment_id=a.id
        )
        db.session.add(cell)
        db.session.commit()
        resp = client.post('/schedule/move-cell', data={
            'cell_id': str(cell.id),
            'day': '2',
            'lesson': '3',
        }, headers={'X-Requested-With': 'XMLHttpRequest'})
        assert resp.status_code == 200

    def test_assignments_for_class_api(self, client, sample_data):
        c = sample_data['classes'][0]
        resp = client.get(f'/schedule/assignments-for-class/{c.id}')
        assert resp.status_code == 200
        data = resp.json
        assert 'assignments' in data
        assert 'classrooms' in data

    def test_auto_schedule_page(self, client, sample_data):
        resp = client.get('/schedule/auto')
        assert resp.status_code == 200

    def test_clear_schedule(self, client, sample_data, db):
        from app.models import ScheduleCell
        a = sample_data['assignments'][0]
        cell = ScheduleCell(
            class_id=a.class_id, day_of_week=1, lesson_number=1,
            assignment_id=a.id
        )
        db.session.add(cell)
        db.session.commit()
        resp = client.post('/schedule/clear', data={
            'school_level': 'elementary',
        }, follow_redirects=True)
        assert resp.status_code == 200


class TestReportRoutes:
    def test_reports_index(self, client, sample_data):
        resp = client.get('/reports/')
        assert resp.status_code == 200

    def test_class_schedule_report(self, client, sample_data):
        c = sample_data['classes'][0]
        resp = client.get(f'/reports/class/{c.id}')
        assert resp.status_code == 200

    def test_teacher_schedule_report(self, client, sample_data):
        t = sample_data['teachers'][0]
        resp = client.get(f'/reports/teacher/{t.id}')
        assert resp.status_code == 200

    def test_export_class_excel(self, client, sample_data):
        c = sample_data['classes'][0]
        resp = client.get(f'/reports/export/class/{c.id}')
        assert resp.status_code == 200
        assert 'spreadsheetml' in resp.content_type

    def test_export_teacher_excel(self, client, sample_data):
        t = sample_data['teachers'][0]
        resp = client.get(f'/reports/export/teacher/{t.id}')
        assert resp.status_code == 200
        assert 'spreadsheetml' in resp.content_type

    def test_export_all_excel(self, client, sample_data):
        resp = client.get('/reports/export/all/elementary')
        assert resp.status_code == 200
        assert 'spreadsheetml' in resp.content_type

    def test_export_all_invalid_level(self, client, sample_data):
        resp = client.get('/reports/export/all/invalid')
        assert resp.status_code == 200


class TestImportRoutes:
    def test_import_index(self, client, db):
        resp = client.get('/import/')
        assert resp.status_code == 200

    def test_import_teachers_no_file(self, client, db):
        resp = client.post('/import/teachers', follow_redirects=True)
        assert resp.status_code == 200

    def test_import_classrooms_no_file(self, client, db):
        resp = client.post('/import/classrooms', follow_redirects=True)
        assert resp.status_code == 200

    def test_import_curriculum_invalid_level(self, client, db):
        resp = client.post('/import/curriculum/invalid', follow_redirects=True)
        assert resp.status_code == 200
