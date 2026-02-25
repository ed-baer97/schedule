"""
Schedule management routes
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app import db
from app.models import SchoolClass, Shift, TeachingAssignment, ScheduleCell, Classroom, ScheduleSettings, Teacher
from app.services.validators import ScheduleValidator
from app.services.auto_scheduler import AutoScheduler

schedule_bp = Blueprint('schedule', __name__)


@schedule_bp.route('/')
def index():
    """Display schedule grid"""
    school_level = request.args.get('school_level', 'elementary')
    shift_id = request.args.get('shift_id', type=int)
    
    # Get shifts for this school level
    shifts = Shift.query.filter_by(school_level=school_level).all()
    
    if not shift_id and shifts:
        shift_id = shifts[0].id
    
    # Get classes for selected shift
    if shift_id:
        classes = SchoolClass.query.filter_by(shift_id=shift_id)\
            .order_by(SchoolClass.grade, SchoolClass.name).all()
    else:
        classes = SchoolClass.query.filter_by(school_level=school_level)\
            .order_by(SchoolClass.grade, SchoolClass.name).all()
    
    # Get schedule settings
    settings = ScheduleSettings.query.filter_by(school_level=school_level).first()
    working_days = settings.working_days if settings else 5
    max_lessons = settings.max_lessons_per_day if settings else 7
    
    # Get schedule cells
    class_ids = [c.id for c in classes]
    cells = ScheduleCell.query.filter(ScheduleCell.class_id.in_(class_ids)).all()
    
    # Build schedule matrix
    schedule = {}
    for cell in cells:
        key = (cell.class_id, cell.day_of_week, cell.lesson_number)
        if key not in schedule:
            schedule[key] = []
        schedule[key].append(cell)
    
    day_names = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']
    scheduler = AutoScheduler()
    classroom_warnings = scheduler.get_classroom_warnings(school_level)
    
    return render_template('schedule/index.html',
                         classes=classes,
                         shifts=shifts,
                         current_shift_id=shift_id,
                         school_level=school_level,
                         schedule=schedule,
                         working_days=working_days,
                         max_lessons=max_lessons,
                         day_names=day_names,
                         schedule_settings=settings,
                         classroom_warnings=classroom_warnings)


@schedule_bp.route('/add-cell', methods=['POST'])
def add_cell():
    """Add lesson to schedule"""
    class_id = int(request.form['class_id'])
    day = int(request.form['day'])
    lesson = int(request.form['lesson'])
    assignment_id = int(request.form['assignment_id'])
    classroom_id = int(request.form['classroom_id']) if request.form.get('classroom_id') else None
    
    assignment = TeachingAssignment.query.get_or_404(assignment_id)
    
    # Validate
    validator = ScheduleValidator()
    errors = validator.validate_cell(
        assignment=assignment,
        day=day,
        lesson=lesson,
        classroom_id=classroom_id
    )
    
    if errors:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'status': 'error', 'errors': errors}), 400
        for error in errors:
            flash(error, 'danger')
        return redirect(url_for('schedule.index'))
    
    # Create cell
    cell = ScheduleCell(
        class_id=class_id,
        day_of_week=day,
        lesson_number=lesson,
        assignment_id=assignment_id,
        classroom_id=classroom_id
    )
    db.session.add(cell)
    db.session.commit()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'status': 'ok', 'cell_id': cell.id})
    
    flash('Урок добавлен в расписание', 'success')
    return redirect(url_for('schedule.index'))


@schedule_bp.route('/remove-cell/<int:id>', methods=['POST'])
def remove_cell(id):
    """Remove lesson from schedule"""
    cell = ScheduleCell.query.get_or_404(id)
    db.session.delete(cell)
    db.session.commit()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'status': 'ok'})
    
    flash('Урок удалён из расписания', 'success')
    return redirect(url_for('schedule.index'))


@schedule_bp.route('/move-cell', methods=['POST'])
def move_cell():
    """Move lesson to another slot"""
    cell_id = int(request.form['cell_id'])
    new_day = int(request.form['day'])
    new_lesson = int(request.form['lesson'])
    new_class_id = int(request.form.get('class_id', 0))
    
    cell = ScheduleCell.query.get_or_404(cell_id)
    
    # Validate new position
    validator = ScheduleValidator()
    errors = validator.validate_cell(
        assignment=cell.assignment,
        day=new_day,
        lesson=new_lesson,
        classroom_id=cell.classroom_id,
        exclude_cell_id=cell_id
    )
    
    if errors:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'status': 'error', 'errors': errors}), 400
        for error in errors:
            flash(error, 'danger')
        return redirect(url_for('schedule.index'))
    
    # Update cell
    cell.day_of_week = new_day
    cell.lesson_number = new_lesson
    if new_class_id:
        cell.class_id = new_class_id
    db.session.commit()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'status': 'ok'})
    
    flash('Урок перемещён', 'success')
    return redirect(url_for('schedule.index'))


@schedule_bp.route('/assignments-for-class/<int:class_id>')
def assignments_for_class(class_id):
    """API: get available assignments for a class (with remaining hours)"""
    assignments = TeachingAssignment.query\
        .filter_by(class_id=class_id)\
        .filter(TeachingAssignment.teacher_id.isnot(None))\
        .all()

    result = []
    for a in assignments:
        if a.remaining_hours > 0:
            result.append({
                'id': a.id,
                'subject_name': a.subject.display_name,
                'subject_color': a.subject.color,
                'teacher_name': a.teacher.display_name if a.teacher else '?',
                'group_number': a.group_number,
                'remaining_hours': a.remaining_hours,
                'preferred_classroom_id': a.preferred_classroom_id,
            })

    classrooms = Classroom.query.order_by(Classroom.number).all()
    classrooms_list = [{'id': c.id, 'display_name': c.display_name} for c in classrooms]

    return jsonify({'assignments': result, 'classrooms': classrooms_list})


@schedule_bp.route('/settings', methods=['GET', 'POST'])
def settings():
    """Schedule settings"""
    if request.method == 'POST':
        school_level = request.form['school_level']
        
        settings = ScheduleSettings.query.filter_by(school_level=school_level).first()
        if not settings:
            settings = ScheduleSettings(school_level=school_level)
            db.session.add(settings)
        
        settings.working_days = int(request.form.get('working_days', 5))
        settings.max_lessons_per_day = int(request.form.get('max_lessons_per_day', 7))
        settings.max_lessons_per_subject_per_day = int(request.form.get('max_lessons_per_subject_per_day', 2))
        settings.classroom_mode = request.form.get('classroom_mode', 'class_room')
        if school_level == 'elementary':
            settings.elementary_group_subjects_leave = 'elementary_group_subjects_leave' in request.form
        db.session.commit()
        
        flash('Настройки сохранены', 'success')
        return redirect(url_for('schedule.settings'))
    
    elementary_settings = ScheduleSettings.query.filter_by(school_level='elementary').first()
    secondary_settings = ScheduleSettings.query.filter_by(school_level='secondary').first()
    
    return render_template('schedule/settings.html',
                         elementary_settings=elementary_settings,
                         secondary_settings=secondary_settings)


@schedule_bp.route('/auto')
def auto_schedule_page():
    """Auto scheduling page"""
    teachers = Teacher.query.order_by(Teacher.full_name).all()
    classes = SchoolClass.query.order_by(SchoolClass.grade, SchoolClass.name).all()
    scheduler = AutoScheduler()
    elementary_warnings = scheduler.get_classroom_warnings('elementary')
    secondary_warnings = scheduler.get_classroom_warnings('secondary')
    elementary_settings = ScheduleSettings.query.filter_by(school_level='elementary').first()
    secondary_settings = ScheduleSettings.query.filter_by(school_level='secondary').first()
    
    return render_template('schedule/auto.html',
                         teachers=teachers,
                         classes=classes,
                         elementary_warnings=elementary_warnings,
                         secondary_warnings=secondary_warnings,
                         elementary_settings=elementary_settings,
                         secondary_settings=secondary_settings)


@schedule_bp.route('/auto/by-teacher', methods=['POST'])
def auto_by_teacher():
    """Auto schedule by teacher (ladder strategy)"""
    teacher_id = int(request.form['teacher_id'])
    school_level = request.form.get('school_level', 'elementary')
    
    scheduler = AutoScheduler()
    count = scheduler.schedule_by_teacher_ladder(teacher_id, school_level)
    
    flash(f'Автоматически распределено уроков: {count}', 'success')
    return redirect(url_for('schedule.index', school_level=school_level))


@schedule_bp.route('/auto/all', methods=['POST'])
def auto_all():
    """Auto schedule all remaining lessons"""
    school_level = request.form.get('school_level', 'elementary')
    
    scheduler = AutoScheduler()
    count = scheduler.auto_schedule_all(school_level)
    
    flash(f'Автоматически распределено уроков: {count}', 'success')
    return redirect(url_for('schedule.index', school_level=school_level))


@schedule_bp.route('/clear', methods=['POST'])
def clear_schedule():
    """Clear schedule"""
    school_level = request.form.get('school_level')
    class_id = request.form.get('class_id')
    teacher_id = request.form.get('teacher_id')
    
    scheduler = AutoScheduler()
    count = scheduler.clear_schedule(
        school_level=school_level,
        class_id=int(class_id) if class_id else None,
        teacher_id=int(teacher_id) if teacher_id else None
    )
    
    flash(f'Удалено уроков из расписания: {count}', 'success')
    return redirect(url_for('schedule.auto_schedule_page'))
