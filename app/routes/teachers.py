"""
Teachers CRUD routes
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from sqlalchemy.orm import joinedload
from app import db
from app.models import Teacher, Classroom

teachers_bp = Blueprint('teachers', __name__)


@teachers_bp.route('/')
def index():
    """List all teachers"""
    teachers = Teacher.query.options(
        joinedload(Teacher.home_classroom)
    ).order_by(Teacher.full_name).all()
    return render_template('teachers/index.html', teachers=teachers)


@teachers_bp.route('/create', methods=['GET', 'POST'])
def create():
    """Create new teacher"""
    classrooms = Classroom.query.order_by(Classroom.number).all()
    if request.method == 'POST':
        teacher = Teacher(
            full_name=request.form['full_name'],
            email=request.form.get('email', ''),
            phone=request.form.get('phone', ''),
            home_classroom_id=int(request.form['home_classroom_id']) if request.form.get('home_classroom_id') else None
        )
        db.session.add(teacher)
        db.session.commit()
        flash('Учитель добавлен', 'success')
        return redirect(url_for('teachers.index'))
    return render_template('teachers/form.html', teacher=None, classrooms=classrooms)


@teachers_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
def edit(id):
    """Edit teacher"""
    teacher = Teacher.query.get_or_404(id)
    classrooms = Classroom.query.order_by(Classroom.number).all()
    if request.method == 'POST':
        teacher.full_name = request.form['full_name']
        teacher.email = request.form.get('email', '')
        teacher.phone = request.form.get('phone', '')
        teacher.home_classroom_id = int(request.form['home_classroom_id']) if request.form.get('home_classroom_id') else None
        db.session.commit()
        flash('Данные учителя обновлены', 'success')
        return redirect(url_for('teachers.index'))
    return render_template('teachers/form.html', teacher=teacher, classrooms=classrooms)


@teachers_bp.route('/<int:id>/delete', methods=['POST'])
def delete(id):
    """Delete teacher"""
    teacher = Teacher.query.get_or_404(id)
    db.session.delete(teacher)
    db.session.commit()
    flash('Учитель удалён', 'success')
    return redirect(url_for('teachers.index'))
