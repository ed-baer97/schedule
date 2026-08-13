"""
Shifts CRUD routes
"""
from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash

from app import db
from app.models import Shift, ShiftLessonTime

shifts_bp = Blueprint('shifts', __name__)

DAY_NAMES_SHORT = (
    (1, 'Понедельник'),
    (2, 'Вторник'),
    (3, 'Среда'),
    (4, 'Четверг'),
    (5, 'Пятница'),
    (6, 'Суббота'),
)

# Верхняя граница сетки дня в форме (HTML max)
FORM_LESSON_GRID_CAP = 10


def _parse_working_days(form):
    try:
        wd = int(form.get('working_days', 5))
    except (TypeError, ValueError):
        return 5
    return 6 if wd == 6 else 5


def _parse_max_lessons_per_day(form, school_level):
    try:
        m = int(form.get('max_lessons_per_day', 7))
    except (TypeError, ValueError):
        m = 5 if school_level == 'elementary' else 7
    return max(1, min(m, FORM_LESSON_GRID_CAP))


def _clamp_shift_bounds(start_lesson, lessons_count, max_lessons_cap):
    """Уроки помещаются в сетку 1..max_lessons_per_day смены."""
    max_cap = max(1, min(int(max_lessons_cap), FORM_LESSON_GRID_CAP))
    start_lesson = max(1, min(int(start_lesson), max_cap))
    max_count = max(1, max_cap - start_lesson + 1)
    lessons_count = max(1, min(int(lessons_count), max_count))
    return start_lesson, lessons_count


def _empty_bell_by_day():
    return {d: {} for d in range(1, 7)}


def _bell_by_day_from_shift(shift):
    out = _empty_bell_by_day()
    if not shift:
        return out
    for lt in shift.lesson_times.all():
        out[lt.day_of_week][lt.lesson_number] = {
            'start': lt.time_start.strftime('%H:%M'),
            'end': lt.time_end.strftime('%H:%M'),
        }
    return out


def _class_hour_bell_from_shift(shift):
    if not shift or not shift.class_hour_day:
        return {}
    day_map = _bell_by_day_from_shift(shift).get(shift.class_hour_day, {})
    return dict(day_map)


def _regular_common_bell_from_shift(shift):
    out = {}
    if not shift:
        return out
    wd = shift.working_days or 5
    class_day = shift.class_hour_day if shift.class_hour_day and shift.class_hour_day <= wd else None
    by_day = _bell_by_day_from_shift(shift)
    start = shift.start_lesson
    end = start + shift.lessons_count
    for n in range(start, end):
        chosen = None
        for d in range(1, min(wd, 6) + 1):
            if class_day and d == class_day:
                continue
            val = by_day.get(d, {}).get(n)
            if val and (val.get('start') or val.get('end')):
                chosen = val
                break
        out[n] = chosen or {'start': '', 'end': ''}
    return out


def _parse_time_hm(s):
    if not s or not str(s).strip():
        return None
    return datetime.strptime(str(s).strip(), '%H:%M').time()


def _apply_class_hour_from_form(shift, form):
    raw_day = (form.get('class_hour_day') or '').strip()
    if not raw_day:
        shift.class_hour_day = None
        shift.class_hour_start = None
        shift.class_hour_end = None
        return
    try:
        d = int(raw_day)
    except ValueError:
        shift.class_hour_day = None
        shift.class_hour_start = None
        shift.class_hour_end = None
        return
    if d < 1 or d > 6:
        shift.class_hour_day = None
        shift.class_hour_start = None
        shift.class_hour_end = None
        return
    shift.class_hour_day = d
    ts = _parse_time_hm(form.get('class_hour_start'))
    te = _parse_time_hm(form.get('class_hour_end'))
    if ts and te and ts < te:
        shift.class_hour_start = ts
        shift.class_hour_end = te
    else:
        flash('Классный час: укажите корректное время начала и конца', 'warning')
        shift.class_hour_start = None
        shift.class_hour_end = None


def _apply_bell_schedule_from_form(shift, form):
    ShiftLessonTime.query.filter_by(shift_id=shift.id).delete()
    start = shift.start_lesson
    wd = shift.working_days or 5
    class_day = shift.class_hour_day if shift.class_hour_day and shift.class_hour_day <= wd else None

    common_by_lesson = {}
    class_day_by_lesson = {}
    for n in range(start, start + shift.lessons_count):
        common_start = (form.get(f'bell_common_start_{n}') or '').strip()
        common_end = (form.get(f'bell_common_end_{n}') or '').strip()
        class_start = (form.get(f'bell_classday_start_{n}') or '').strip()
        class_end = (form.get(f'bell_classday_end_{n}') or '').strip()

        def parse_pair(label, s, e):
            if not s and not e:
                return None
            if not s or not e:
                flash(f'{label}, урок {n}: укажите оба времени или оставьте пустым', 'warning')
                return None
            try:
                ts = datetime.strptime(s, '%H:%M').time()
                te = datetime.strptime(e, '%H:%M').time()
            except ValueError:
                flash(f'{label}, урок {n}: неверный формат времени', 'warning')
                return None
            if ts >= te:
                flash(f'{label}, урок {n}: конец позже начала', 'warning')
                return None
            return (ts, te)

        common_by_lesson[n] = parse_pair('Остальные дни', common_start, common_end)
        class_day_by_lesson[n] = parse_pair('День классного часа', class_start, class_end)

    for day in range(1, min(wd, 6) + 1):
        for n in range(start, start + shift.lessons_count):
            if class_day and day == class_day:
                pair = class_day_by_lesson.get(n)
            else:
                pair = common_by_lesson.get(n)
            if not pair:
                continue
            ts, te = pair
            db.session.add(ShiftLessonTime(
                shift_id=shift.id,
                day_of_week=day,
                lesson_number=n,
                time_start=ts,
                time_end=te,
            ))


@shifts_bp.route('/')
def index():
    """List all shifts"""
    shifts = Shift.query.order_by(Shift.school_level, Shift.name).all()
    return render_template('shifts/index.html', shifts=shifts)


@shifts_bp.route('/create', methods=['GET', 'POST'])
def create():
    """Create new shift"""
    default_start = 1
    default_count = 6
    if request.method == 'POST':
        school_level = request.form['school_level']
        working_days = _parse_working_days(request.form)
        max_lessons_per_day = _parse_max_lessons_per_day(request.form, school_level)
        start_lesson, lessons_count = _clamp_shift_bounds(
            int(request.form.get('start_lesson', 1)),
            int(request.form.get('lessons_count', 6)),
            max_lessons_per_day,
        )
        shift = Shift(
            name=request.form['name'],
            school_level=school_level,
            start_lesson=start_lesson,
            lessons_count=lessons_count,
            working_days=working_days,
            max_lessons_per_day=max_lessons_per_day,
        )
        _apply_class_hour_from_form(shift, request.form)
        if shift.class_hour_day and shift.class_hour_day > working_days:
            shift.class_hour_day = None
            shift.class_hour_start = None
            shift.class_hour_end = None
            flash('Классный час: выбран суббота при 5-дневной неделе — сброшен', 'warning')
        db.session.add(shift)
        db.session.flush()
        _apply_bell_schedule_from_form(shift, request.form)
        db.session.commit()
        flash('Смена добавлена', 'success')
        return redirect(url_for('shifts.index'))

    max_lessons_cap = FORM_LESSON_GRID_CAP
    max_lessons_count_allowed = max(1, max_lessons_cap - default_start + 1)
    return render_template(
        'shifts/form.html',
        shift=None,
        working_days=5,
        max_lessons_per_day=7,
        start_lesson=default_start,
        lessons_count=min(default_count, max_lessons_count_allowed),
        max_lessons_cap=max_lessons_cap,
        max_lessons_count_allowed=max_lessons_count_allowed,
        bell_by_day=_empty_bell_by_day(),
        class_hour_bell={},
        regular_bell_common={n: {'start': '', 'end': ''} for n in range(default_start, default_start + min(default_count, max_lessons_count_allowed))},
        day_names_short=DAY_NAMES_SHORT,
    )


@shifts_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
def edit(id):
    """Edit shift"""
    shift = Shift.query.get_or_404(id)
    max_lessons_cap = shift.max_lessons_per_day
    if request.method == 'POST':
        shift.name = request.form['name']
        school_level = request.form['school_level']
        shift.school_level = school_level
        working_days = _parse_working_days(request.form)
        max_lessons_per_day = _parse_max_lessons_per_day(request.form, school_level)
        shift.working_days = working_days
        shift.max_lessons_per_day = max_lessons_per_day
        start_lesson, lessons_count = _clamp_shift_bounds(
            int(request.form.get('start_lesson', 1)),
            int(request.form.get('lessons_count', 6)),
            max_lessons_per_day,
        )
        shift.start_lesson = start_lesson
        shift.lessons_count = lessons_count
        _apply_class_hour_from_form(shift, request.form)
        if shift.class_hour_day and shift.class_hour_day > working_days:
            shift.class_hour_day = None
            shift.class_hour_start = None
            shift.class_hour_end = None
            flash('Классный час: выбран день вне учебной недели — сброшен', 'warning')
        _apply_bell_schedule_from_form(shift, request.form)
        db.session.commit()
        flash('Данные смены обновлены', 'success')
        return redirect(url_for('shifts.index'))
    start_lesson, lessons_count = _clamp_shift_bounds(
        shift.start_lesson, shift.lessons_count, shift.max_lessons_per_day
    )
    max_lessons_count_allowed = max(1, max_lessons_cap - start_lesson + 1)
    return render_template(
        'shifts/form.html',
        shift=shift,
        working_days=shift.working_days,
        max_lessons_per_day=shift.max_lessons_per_day,
        start_lesson=start_lesson,
        lessons_count=lessons_count,
        max_lessons_cap=max_lessons_cap,
        max_lessons_count_allowed=max_lessons_count_allowed,
        bell_by_day=_bell_by_day_from_shift(shift),
        class_hour_bell=_class_hour_bell_from_shift(shift),
        regular_bell_common=_regular_common_bell_from_shift(shift),
        day_names_short=DAY_NAMES_SHORT,
    )


@shifts_bp.route('/<int:id>/delete', methods=['POST'])
def delete(id):
    """Delete shift"""
    shift = Shift.query.get_or_404(id)
    db.session.delete(shift)
    db.session.commit()
    flash('Смена удалена', 'success')
    return redirect(url_for('shifts.index'))
