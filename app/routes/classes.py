"""
School Classes CRUD routes
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from sqlalchemy.orm import joinedload
from app import db
from app.models import SchoolClass, Shift, Classroom

classes_bp = Blueprint('classes', __name__)


def _grade_from_name(name):
    """Extract grade (1-11) from class name, e.g. '5А' -> 5, '10Б' -> 10"""
    grade_str = ''.join(filter(str.isdigit, name))
    return int(grade_str) if grade_str else 1


@classes_bp.route('/')
def index():
    """List all school classes"""
    classes = SchoolClass.query.options(
        joinedload(SchoolClass.home_classroom)
    ).order_by(SchoolClass.grade, SchoolClass.name).all()
    shifts = Shift.query.order_by(Shift.school_level, Shift.name).all()
    return render_template('classes/index.html', classes=classes, shifts=shifts)


@classes_bp.route('/batch-shift', methods=['POST'])
def batch_update_shift():
    """Mass-update shift for selected classes"""
    class_ids = request.form.getlist('class_ids', type=int)
    shift_id = request.form.get('shift_id', type=int)
    if not class_ids:
        flash('Выберите хотя бы один класс', 'warning')
        return redirect(url_for('classes.index'))
    new_shift_id = shift_id if shift_id else None

    SchoolClass.query.filter(SchoolClass.id.in_(class_ids)).update(
        {SchoolClass.shift_id: new_shift_id}, synchronize_session=False
    )
    db.session.commit()
    flash(f'Смена обновлена для {len(class_ids)} классов', 'success')
    return redirect(url_for('classes.index'))


@classes_bp.route('/create', methods=['GET', 'POST'])
def create():
    """Create new school class"""
    shifts = Shift.query.all()
    classrooms = Classroom.query.order_by(Classroom.number).all()
    if request.method == 'POST':
        name = request.form['name'].strip()
        school_class = SchoolClass(
            name=name,
            grade=_grade_from_name(name),
            school_level=request.form['school_level'],
            shift_id=int(request.form['shift_id']) if request.form.get('shift_id') else None,
            home_classroom_id=int(request.form['home_classroom_id']) if request.form.get('home_classroom_id') else None
        )
        db.session.add(school_class)
        db.session.commit()
        flash('Класс добавлен', 'success')
        return redirect(url_for('classes.index'))
    return render_template('classes/form.html', school_class=None, shifts=shifts, classrooms=classrooms)


@classes_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
def edit(id):
    """Edit school class"""
    school_class = SchoolClass.query.get_or_404(id)
    shifts = Shift.query.all()
    classrooms = Classroom.query.order_by(Classroom.number).all()
    if request.method == 'POST':
        name = request.form['name'].strip()
        school_class.name = name
        school_class.grade = _grade_from_name(name)
        school_class.school_level = request.form['school_level']
        school_class.shift_id = int(request.form['shift_id']) if request.form.get('shift_id') else None
        school_class.home_classroom_id = int(request.form['home_classroom_id']) if request.form.get('home_classroom_id') else None
        db.session.commit()
        flash('Данные класса обновлены', 'success')
        return redirect(url_for('classes.index'))
    return render_template('classes/form.html', school_class=school_class, shifts=shifts, classrooms=classrooms)


@classes_bp.route('/<int:id>/delete', methods=['POST'])
def delete(id):
    """Delete school class"""
    school_class = SchoolClass.query.get_or_404(id)
    db.session.delete(school_class)
    db.session.commit()
    flash('Класс удалён', 'success')
    return redirect(url_for('classes.index'))
