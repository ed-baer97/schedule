"""
Shifts CRUD routes
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app import db
from app.models import Shift

shifts_bp = Blueprint('shifts', __name__)


@shifts_bp.route('/')
def index():
    """List all shifts"""
    shifts = Shift.query.order_by(Shift.school_level, Shift.name).all()
    return render_template('shifts/index.html', shifts=shifts)


@shifts_bp.route('/create', methods=['GET', 'POST'])
def create():
    """Create new shift"""
    if request.method == 'POST':
        shift = Shift(
            name=request.form['name'],
            school_level=request.form['school_level'],
            start_lesson=int(request.form.get('start_lesson', 1)),
            lessons_count=int(request.form.get('lessons_count', 6))
        )
        db.session.add(shift)
        db.session.commit()
        flash('Смена добавлена', 'success')
        return redirect(url_for('shifts.index'))
    return render_template('shifts/form.html', shift=None)


@shifts_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
def edit(id):
    """Edit shift"""
    shift = Shift.query.get_or_404(id)
    if request.method == 'POST':
        shift.name = request.form['name']
        shift.school_level = request.form['school_level']
        shift.start_lesson = int(request.form.get('start_lesson', 1))
        shift.lessons_count = int(request.form.get('lessons_count', 6))
        db.session.commit()
        flash('Данные смены обновлены', 'success')
        return redirect(url_for('shifts.index'))
    return render_template('shifts/form.html', shift=shift)


@shifts_bp.route('/<int:id>/delete', methods=['POST'])
def delete(id):
    """Delete shift"""
    shift = Shift.query.get_or_404(id)
    db.session.delete(shift)
    db.session.commit()
    flash('Смена удалена', 'success')
    return redirect(url_for('shifts.index'))
