"""
Teaching assignments routes (assign teachers to subjects/classes)
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app import db
from app.models import Teacher, SchoolClass, Subject, TeachingAssignment

assignments_bp = Blueprint('assignments', __name__)


@assignments_bp.route('/')
def index():
    """List all teaching assignments"""
    school_level = request.args.get('school_level', 'elementary')
    
    assignments = TeachingAssignment.query\
        .join(SchoolClass)\
        .filter(SchoolClass.school_level == school_level)\
        .order_by(SchoolClass.grade, SchoolClass.name)\
        .all()
    
    teachers = Teacher.query.order_by(Teacher.full_name).all()
    
    return render_template('assignments/index.html',
                         assignments=assignments,
                         teachers=teachers,
                         school_level=school_level)


@assignments_bp.route('/create', methods=['GET', 'POST'])
def create():
    """Create new teaching assignment"""
    teachers = Teacher.query.order_by(Teacher.full_name).all()
    classes = SchoolClass.query.order_by(SchoolClass.grade, SchoolClass.name).all()
    subjects = Subject.query.order_by(Subject.name).all()
    
    if request.method == 'POST':
        assignment = TeachingAssignment(
            subject_id=int(request.form['subject_id']),
            teacher_id=int(request.form['teacher_id']) if request.form.get('teacher_id') else None,
            class_id=int(request.form['class_id']),
            hours_per_week=int(request.form['hours_per_week']),
            group_number=int(request.form['group_number']) if request.form.get('group_number') else None,
            preferred_classroom_id=int(request.form['preferred_classroom_id']) if request.form.get('preferred_classroom_id') else None
        )
        db.session.add(assignment)
        db.session.commit()
        flash('Назначение создано', 'success')
        return redirect(url_for('assignments.index'))
    
    return render_template('assignments/form.html',
                         assignment=None,
                         teachers=teachers,
                         classes=classes,
                         subjects=subjects)


@assignments_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
def edit(id):
    """Edit teaching assignment"""
    assignment = TeachingAssignment.query.get_or_404(id)
    teachers = Teacher.query.order_by(Teacher.full_name).all()
    classes = SchoolClass.query.order_by(SchoolClass.grade, SchoolClass.name).all()
    subjects = Subject.query.order_by(Subject.name).all()
    
    if request.method == 'POST':
        assignment.subject_id = int(request.form['subject_id'])
        assignment.teacher_id = int(request.form['teacher_id']) if request.form.get('teacher_id') else None
        assignment.class_id = int(request.form['class_id'])
        assignment.hours_per_week = int(request.form['hours_per_week'])
        assignment.group_number = int(request.form['group_number']) if request.form.get('group_number') else None
        assignment.preferred_classroom_id = int(request.form['preferred_classroom_id']) if request.form.get('preferred_classroom_id') else None
        db.session.commit()
        flash('Назначение обновлено', 'success')
        return redirect(url_for('assignments.index'))
    
    return render_template('assignments/form.html',
                         assignment=assignment,
                         teachers=teachers,
                         classes=classes,
                         subjects=subjects)


@assignments_bp.route('/<int:id>/assign-teacher', methods=['POST'])
def assign_teacher(id):
    """Quick assign teacher to existing assignment"""
    assignment = TeachingAssignment.query.get_or_404(id)
    teacher_id = request.form.get('teacher_id')
    assignment.teacher_id = int(teacher_id) if teacher_id else None
    db.session.commit()
    flash('Учитель назначен', 'success')
    return redirect(url_for('assignments.index', school_level=assignment.school_class.school_level))


@assignments_bp.route('/<int:id>/delete', methods=['POST'])
def delete(id):
    """Delete teaching assignment"""
    assignment = TeachingAssignment.query.get_or_404(id)
    school_level = assignment.school_class.school_level
    db.session.delete(assignment)
    db.session.commit()
    flash('Назначение удалено', 'success')
    return redirect(url_for('assignments.index', school_level=school_level))


