"""
Workload management routes (hours per subject per class)
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app import db
from app.models import SchoolClass, Subject, TeachingAssignment

workload_bp = Blueprint('workload', __name__)


@workload_bp.route('/')
def index():
    """Display workload table (classes x subjects)"""
    school_level = request.args.get('school_level', 'elementary')
    
    classes = SchoolClass.query.filter_by(school_level=school_level)\
        .order_by(SchoolClass.grade, SchoolClass.name).all()
    subjects = Subject.query.order_by(Subject.name).all()
    
    # Build workload matrix
    workload = {}
    assignments = TeachingAssignment.query.join(SchoolClass)\
        .filter(SchoolClass.school_level == school_level).all()
    
    for assignment in assignments:
        key = (assignment.class_id, assignment.subject_id)
        if key not in workload:
            workload[key] = 0
        workload[key] += assignment.hours_per_week
    
    return render_template('workload/index.html',
                         classes=classes,
                         subjects=subjects,
                         workload=workload,
                         school_level=school_level)


@workload_bp.route('/update', methods=['POST'])
def update():
    """Update hours for a class-subject pair"""
    class_id = int(request.form['class_id'])
    subject_id = int(request.form['subject_id'])
    hours = int(request.form['hours'])
    
    # Find existing assignment without teacher
    assignment = TeachingAssignment.query.filter_by(
        class_id=class_id,
        subject_id=subject_id,
        teacher_id=None
    ).first()
    
    if hours == 0:
        # Remove if exists
        if assignment:
            db.session.delete(assignment)
            db.session.commit()
    else:
        if assignment:
            assignment.hours_per_week = hours
        else:
            assignment = TeachingAssignment(
                class_id=class_id,
                subject_id=subject_id,
                hours_per_week=hours,
                teacher_id=None
            )
            db.session.add(assignment)
        db.session.commit()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'status': 'ok'})
    
    flash('Нагрузка обновлена', 'success')
    return redirect(url_for('workload.index'))
