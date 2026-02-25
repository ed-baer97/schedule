"""
Main routes - home page and navigation
"""
from flask import Blueprint, render_template
from app.models import Teacher, SchoolClass, Subject, Classroom, TeachingAssignment, ScheduleCell

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    """Home page"""
    stats = {
        'teachers_count': Teacher.query.count(),
        'classes_count': SchoolClass.query.count(),
        'subjects_count': Subject.query.count(),
        'classrooms_count': Classroom.query.count(),
    }
    for level in ('elementary', 'secondary'):
        class_ids = [r[0] for r in SchoolClass.query.filter_by(school_level=level).with_entities(SchoolClass.id).all()]
        stats[f'{level}_classes'] = len(class_ids)
        stats[f'{level}_assignments'] = TeachingAssignment.query.filter(TeachingAssignment.class_id.in_(class_ids)).count() if class_ids else 0
        stats[f'{level}_scheduled'] = ScheduleCell.query.filter(ScheduleCell.class_id.in_(class_ids)).count() if class_ids else 0
    return render_template('index.html', **stats)
