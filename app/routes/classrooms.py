"""
Classrooms CRUD routes
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app import db
from app.models import Classroom

classrooms_bp = Blueprint('classrooms', __name__)


@classrooms_bp.route('/')
def index():
    """List all classrooms grouped by floor"""
    classrooms = Classroom.query.order_by(
        db.func.coalesce(Classroom.floor, 999).asc(),
        Classroom.number
    ).all()
    return render_template('classrooms/index.html', classrooms=classrooms)


@classrooms_bp.route('/create', methods=['GET', 'POST'])
def create():
    """Create new classroom"""
    if request.method == 'POST':
        cap = request.form.get('classes_capacity', '1')
        classroom = Classroom(
            number=request.form['number'],
            name=request.form.get('name', ''),
            floor=int(request.form['floor']) if request.form.get('floor') else None,
            building=request.form.get('building', ''),
            classes_capacity=int(cap) if cap and cap.isdigit() else 1
        )
        db.session.add(classroom)
        db.session.commit()
        flash('Кабинет добавлен', 'success')
        return redirect(url_for('classrooms.index'))
    return render_template('classrooms/form.html', classroom=None)


@classrooms_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
def edit(id):
    """Edit classroom"""
    classroom = Classroom.query.get_or_404(id)
    if request.method == 'POST':
        classroom.number = request.form['number']
        classroom.name = request.form.get('name', '')
        classroom.floor = int(request.form['floor']) if request.form.get('floor') else None
        classroom.building = request.form.get('building', '')
        cap = request.form.get('classes_capacity', '1')
        classroom.classes_capacity = int(cap) if cap and cap.isdigit() else 1
        db.session.commit()
        flash('Данные кабинета обновлены', 'success')
        return redirect(url_for('classrooms.index'))
    return render_template('classrooms/form.html', classroom=classroom)


@classrooms_bp.route('/<int:id>/delete', methods=['POST'])
def delete(id):
    """Delete classroom"""
    classroom = Classroom.query.get_or_404(id)
    db.session.delete(classroom)
    db.session.commit()
    flash('Кабинет удалён', 'success')
    return redirect(url_for('classrooms.index'))
