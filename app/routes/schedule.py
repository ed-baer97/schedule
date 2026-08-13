"""
Schedule management routes
"""
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, Response, stream_with_context
from app import db
from app.models import SchoolClass, Shift, TeachingAssignment, ScheduleCell, Classroom, ScheduleSettings, Teacher
from app.services.validators import ScheduleValidator
from app.services.auto_scheduler import AutoScheduler

schedule_bp = Blueprint('schedule', __name__)


def _grid_redirect(class_id=None, day=None, lesson=None, school_class=None):
    """Stay on the same school/shift and cell after add/move/delete."""
    if school_class is None and class_id:
        school_class = SchoolClass.query.get(class_id)
    school_level = request.form.get('school_level') or request.args.get('school_level')
    shift_id = request.form.get('shift_id', type=int) or request.args.get('shift_id', type=int)
    if school_class is not None:
        school_level = school_level or school_class.school_level
        if shift_id is None:
            shift_id = school_class.shift_id
        if class_id is None:
            class_id = school_class.id
    url = url_for(
        'schedule.index',
        school_level=school_level or 'elementary',
        shift_id=shift_id,
    )
    if class_id is not None and day is not None and lesson is not None:
        url += f'#slot-{class_id}-{day}-{lesson}'
    elif day:
        url += f'#day-{day}'
    return redirect(url)


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
    
    # Get schedule settings (режим кабинетов и т.д.) и сетку недели/дня по смене
    settings = ScheduleSettings.query.filter_by(school_level=school_level).first()
    current_shift = Shift.query.get(shift_id) if shift_id else None
    if current_shift:
        working_days = current_shift.working_days
        max_lessons = current_shift.max_lessons_per_day
    else:
        working_days = 5
        max_lessons = 7
    
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

    lesson_times_by_day = {}
    class_hour_time_label = ''
    lessons_range = list(range(1, max_lessons + 1))

    if current_shift:
        for lt in current_shift.lesson_times.all():
            lesson_times_by_day.setdefault(lt.day_of_week, {})[lt.lesson_number] = (
                f'{lt.time_start.strftime("%H:%M")}–{lt.time_end.strftime("%H:%M")}'
            )
        lessons_range = list(range(
            current_shift.start_lesson,
            current_shift.start_lesson + current_shift.lessons_count,
        ))
        if (
            current_shift.class_hour_start
            and current_shift.class_hour_end
        ):
            class_hour_time_label = (
                f'{current_shift.class_hour_start.strftime("%H:%M")}–'
                f'{current_shift.class_hour_end.strftime("%H:%M")}'
            )

    return render_template('schedule/index.html',
                         classes=classes,
                         shifts=shifts,
                         current_shift_id=shift_id,
                         current_shift=current_shift,
                         school_level=school_level,
                         schedule=schedule,
                         working_days=working_days,
                         max_lessons=max_lessons,
                         lessons_range=lessons_range,
                         day_names=day_names,
                         schedule_settings=settings,
                         classroom_warnings=classroom_warnings,
                         lesson_times_by_day=lesson_times_by_day,
                         class_hour_time_label=class_hour_time_label)


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
        return _grid_redirect(class_id=class_id, day=day, lesson=lesson)
    
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
        return jsonify({
            'status': 'ok',
            'cell_id': cell.id,
            'anchor': f'slot-{class_id}-{day}-{lesson}',
        })
    
    flash('Урок добавлен в расписание', 'success')
    return _grid_redirect(class_id=class_id, day=day, lesson=lesson)


@schedule_bp.route('/remove-cell/<int:id>', methods=['POST'])
def remove_cell(id):
    """Remove lesson from schedule"""
    cell = ScheduleCell.query.get_or_404(id)
    class_id, day, lesson = cell.class_id, cell.day_of_week, cell.lesson_number
    school_class = cell.school_class
    db.session.delete(cell)
    db.session.commit()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'status': 'ok',
            'anchor': f'slot-{class_id}-{day}-{lesson}',
        })
    
    flash('Урок удалён из расписания', 'success')
    return _grid_redirect(class_id=class_id, day=day, lesson=lesson, school_class=school_class)


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
        return _grid_redirect(
            class_id=new_class_id or cell.class_id,
            day=new_day,
            lesson=new_lesson,
        )
    
    # Update cell
    cell.day_of_week = new_day
    cell.lesson_number = new_lesson
    if new_class_id:
        cell.class_id = new_class_id
    db.session.commit()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'status': 'ok',
            'anchor': f'slot-{cell.class_id}-{new_day}-{new_lesson}',
        })
    
    flash('Урок перемещён', 'success')
    return _grid_redirect(class_id=cell.class_id, day=new_day, lesson=new_lesson)


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
                'subject_color': a.subject.display_color,
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
    
    shifts_elementary = Shift.query.filter_by(school_level='elementary').order_by(Shift.name).all()
    shifts_secondary = Shift.query.filter_by(school_level='secondary').order_by(Shift.name).all()

    return render_template('schedule/auto.html',
                         teachers=teachers,
                         classes=classes,
                         elementary_warnings=elementary_warnings,
                         secondary_warnings=secondary_warnings,
                         elementary_settings=elementary_settings,
                         secondary_settings=secondary_settings,
                         shifts_elementary=shifts_elementary,
                         shifts_secondary=shifts_secondary)


@schedule_bp.route('/auto/by-teacher', methods=['POST'])
def auto_by_teacher():
    """Auto schedule by teacher (ladder strategy)"""
    teacher_id = int(request.form['teacher_id'])
    school_level = request.form.get('school_level', 'elementary')
    diagnose = request.form.get('diagnose') in ('1', 'true', 'on')
    
    scheduler = AutoScheduler()
    done = scheduler.schedule_by_teacher_ladder_result(teacher_id, school_level)
    count = done.get('count', 0)
    solver_placed = done.get('solver_placed_count', 0)
    unplaced = done.get('unplaced', [])
    diagnostics = done.get('diagnostics', [])
    
    flash(f'Автоматически распределено уроков: {count}', 'success')
    if done.get('solver_used'):
        flash(
            f'Графовый solver-pass: добавлено {solver_placed}, остаток назначений {len(unplaced)}',
            'info'
        )
    if diagnose:
        items = diagnostics[:10]
        if items:
            first = items[0]
            reason = first['top_reasons'][0]['reason'] if first['top_reasons'] else 'Нет подходящих слотов'
            flash(
                f'Диагностика: осталось назначений {len(items)}. '
                f'Пример: {first["class_name"]} — {first["subject_name"]}, '
                f'остаток {first["remaining_hours"]}, причина: {reason}',
                'warning'
            )
        else:
            flash('Диагностика: остатка по выбранному учителю нет.', 'info')
    return redirect(url_for('schedule.index', school_level=school_level))


@schedule_bp.route('/auto/all', methods=['POST'])
def auto_all():
    """Auto schedule all remaining lessons"""
    school_level = request.form.get('school_level', 'elementary')
    diagnose = request.form.get('diagnose') in ('1', 'true', 'on')
    solver = request.form.get('solver', 'legacy')
    shift_id = request.form.get('shift_id', type=int)
    time_limit_sec = request.form.get('time_limit_sec', type=float) or 60.0
    random_seed = request.form.get('random_seed', type=int) or 1

    scheduler = AutoScheduler()
    done = scheduler.auto_schedule_all_result(
        school_level,
        solver=solver,
        shift_id=shift_id,
        time_limit_sec=time_limit_sec,
        random_seed=random_seed,
    )
    if done.get('type') == 'error':
        flash(done.get('message', 'Ошибка автозаполнения'), 'danger')
        return redirect(url_for('schedule.auto_schedule_page'))

    count = done.get('count', 0)
    solver_placed = done.get('solver_placed_count', 0)
    unplaced = done.get('unplaced', [])
    diagnostics = done.get('diagnostics', [])

    if solver == 'cp_sat_mvp':
        flash(
            f'CP-SAT: статус {done.get("cp_sat_status", "?")}, '
            f'размещено уроков: {count}, время решения: {done.get("wall_time_sec")} с',
            'success' if done.get('cp_sat_status') in ('OPTIMAL', 'FEASIBLE') else 'warning',
        )
        if done.get('metrics_before') is not None and done.get('metrics_after') is not None:
            mb = done['metrics_before']
            ma = done['metrics_after']
            flash(
                f'Окна (промежутки): было {mb.get("teacher_window_gaps", "?")}, '
                f'стало {ma.get("teacher_window_gaps", "?")}; '
                f'баланс дней (штраф): было {mb.get("class_load_penalty", "?")}, '
                f'стало {ma.get("class_load_penalty", "?")}',
                'info',
            )
    else:
        flash(f'Автоматически распределено уроков: {count}', 'success')
    if done.get('solver_used') and solver != 'cp_sat_mvp':
        flash(
            f'Графовый solver-pass: добавлено {solver_placed}, остаток назначений {len(unplaced)}',
            'info'
        )
    if diagnose:
        items = diagnostics[:10]
        if items:
            first = items[0]
            reason = first['top_reasons'][0]['reason'] if first['top_reasons'] else 'Нет подходящих слотов'
            flash(
                f'Диагностика: осталось назначений {len(items)}. '
                f'Пример: {first["class_name"]} — {first["subject_name"]}, '
                f'остаток {first["remaining_hours"]}, причина: {reason}',
                'warning'
            )
        else:
            flash('Диагностика: остатка по уровню нет.', 'info')
    return redirect(url_for('schedule.index', school_level=school_level))


def _ndjson_stream(generator):
    """Поток NDJSON для прогресса автозаполнения."""

    def generate():
        scheduler = AutoScheduler()
        try:
            for event in generator(scheduler):
                yield json.dumps(event, ensure_ascii=False) + '\n'
        except Exception as e:
            yield json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False) + '\n'

    return Response(
        stream_with_context(generate()),
        mimetype='application/x-ndjson',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@schedule_bp.route('/auto/all/stream', methods=['POST'])
def auto_all_stream():
    """Потоковое автозаполнение всего расписания с прогрессом."""
    if request.is_json and request.json:
        school_level = request.json.get('school_level', 'elementary')
        diagnose = bool(request.json.get('diagnose'))
        solver = request.json.get('solver', 'legacy')
        shift_id = request.json.get('shift_id')
        shift_id = int(shift_id) if shift_id is not None else None
        time_limit_sec = float(request.json.get('time_limit_sec') or 60)
        random_seed = int(request.json.get('random_seed') or 1)
    else:
        school_level = request.form.get('school_level', 'elementary')
        diagnose = request.form.get('diagnose') in ('1', 'true', 'on')
        solver = request.form.get('solver', 'legacy')
        shift_id = request.form.get('shift_id', type=int)
        time_limit_sec = float(request.form.get('time_limit_sec') or 60)
        random_seed = int(request.form.get('random_seed') or 1)

    def gen(scheduler):
        for event in scheduler.auto_schedule_all_iter(
            school_level,
            solver=solver,
            shift_id=shift_id,
            time_limit_sec=time_limit_sec,
            random_seed=random_seed,
        ):
            if event.get('type') == 'done' and not diagnose:
                event.pop('diagnostics', None)
            yield event

    return _ndjson_stream(gen)


@schedule_bp.route('/auto/by-teacher/stream', methods=['POST'])
def auto_by_teacher_stream():
    """Потоковое автозаполнение по учителю с прогрессом."""
    if request.is_json and request.json:
        teacher_id = int(request.json['teacher_id'])
        school_level = request.json.get('school_level', 'elementary')
        diagnose = bool(request.json.get('diagnose'))
    else:
        teacher_id = int(request.form['teacher_id'])
        school_level = request.form.get('school_level', 'elementary')
        diagnose = request.form.get('diagnose') in ('1', 'true', 'on')

    def gen(scheduler):
        for event in scheduler.schedule_by_teacher_ladder_iter(teacher_id, school_level):
            if event.get('type') == 'done' and not diagnose:
                event.pop('diagnostics', None)
            yield event

    return _ndjson_stream(gen)


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
