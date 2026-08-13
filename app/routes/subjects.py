"""
Subjects CRUD routes
"""
import re

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app import db
from app.models import Subject, Teacher, SchoolClass, TeachingAssignment, Classroom, ScheduleCell

subjects_bp = Blueprint('subjects', __name__)

_HEX_COLOR = re.compile(r'^#[0-9A-Fa-f]{6}$')


def _reassign_cells_and_delete_assignment(assignment, target_assignment_id):
    """Move schedule cells to another assignment, flush, then delete (avoids FK NULL on delete)."""
    cells = ScheduleCell.query.filter_by(assignment_id=assignment.id).all()
    for cell in cells:
        cell.assignment_id = target_assignment_id
    if cells:
        db.session.flush()
    db.session.delete(assignment)


def _parse_subject_color(form):
    raw = (form.get('color') or '').strip()
    if raw and _HEX_COLOR.match(raw):
        return raw
    return Subject.DEFAULT_COLOR


@subjects_bp.route('/')
def index():
    """Two-level navigation: level choice or subject list by level"""
    school_level = request.args.get('school_level')
    if not school_level:
        return render_template(
            'subjects/index.html',
            school_level=None,
            subjects=[],
            color_palette=Subject.COLOR_PALETTE,
        )
    if school_level not in ('elementary', 'secondary'):
        return redirect(url_for('subjects.index'))
    subject_ids = db.session.query(TeachingAssignment.subject_id)\
        .join(SchoolClass)\
        .filter(SchoolClass.school_level == school_level)\
        .distinct().all()
    subject_ids = [s[0] for s in subject_ids]
    subjects = Subject.query.filter(Subject.id.in_(subject_ids))\
        .order_by(Subject.name).all() if subject_ids else []
    return render_template(
        'subjects/index.html',
        school_level=school_level,
        subjects=subjects,
        color_palette=Subject.COLOR_PALETTE,
    )


@subjects_bp.route('/create', methods=['GET', 'POST'])
def create():
    """Create new subject"""
    classrooms = Classroom.query.order_by(Classroom.number).all()
    if request.method == 'POST':
        subject = Subject(
            name=request.form['name'],
            color=_parse_subject_color(request.form),
            requires_fixed_classroom='requires_fixed_classroom' in request.form,
            default_classroom_id=int(request.form['default_classroom_id']) if request.form.get('default_classroom_id') else None
        )
        db.session.add(subject)
        db.session.commit()
        flash('Предмет добавлен', 'success')
        return redirect(url_for('subjects.index'))
    return render_template(
        'subjects/form.html',
        subject=None,
        classrooms=classrooms,
        default_subject_color=Subject.DEFAULT_COLOR,
        color_palette=Subject.COLOR_PALETTE,
    )


@subjects_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
def edit(id):
    """Edit subject"""
    subject = Subject.query.get_or_404(id)
    classrooms = Classroom.query.order_by(Classroom.number).all()
    if request.method == 'POST':
        subject.name = request.form['name']
        subject.color = _parse_subject_color(request.form)
        subject.requires_fixed_classroom = 'requires_fixed_classroom' in request.form
        subject.default_classroom_id = int(request.form['default_classroom_id']) if request.form.get('default_classroom_id') else None
        db.session.commit()
        flash('Данные предмета обновлены', 'success')
        return redirect(url_for('subjects.index'))
    return render_template(
        'subjects/form.html',
        subject=subject,
        classrooms=classrooms,
        default_subject_color=Subject.DEFAULT_COLOR,
        color_palette=Subject.COLOR_PALETTE,
    )


@subjects_bp.route('/<int:id>/delete', methods=['POST'])
def delete(id):
    """Delete subject"""
    subject = Subject.query.get_or_404(id)
    db.session.delete(subject)
    db.session.commit()
    flash('Предмет удалён', 'success')
    return redirect(url_for('subjects.index'))


@subjects_bp.route('/<int:id>/set-color', methods=['POST'])
def set_color(id):
    """Быстрое изменение цвета со списка предметов (клик по превью)."""
    subject = Subject.query.get_or_404(id)
    subject.color = _parse_subject_color(request.form)
    db.session.commit()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'ok': True, 'color': subject.display_color})
    school_level = request.form.get('school_level') or request.args.get('school_level')
    flash('Цвет сохранён', 'success')
    if school_level in ('elementary', 'secondary'):
        return redirect(url_for('subjects.index', school_level=school_level))
    return redirect(url_for('subjects.index'))


@subjects_bp.route('/<int:id>/assignments')
def assignments(id):
    """View/manage teacher assignments for a subject (teacher-centric UI)"""
    subject = Subject.query.get_or_404(id)
    school_level = request.args.get('school_level', 'elementary')

    class_ids = db.session.query(TeachingAssignment.class_id)\
        .join(SchoolClass)\
        .filter(
            TeachingAssignment.subject_id == subject.id,
            SchoolClass.school_level == school_level
        ).distinct().all()
    class_ids = [c[0] for c in class_ids]

    classes = SchoolClass.query.filter(SchoolClass.id.in_(class_ids))\
        .order_by(SchoolClass.grade, SchoolClass.name).all() if class_ids else []

    subject_assignments = TeachingAssignment.query\
        .join(SchoolClass)\
        .filter(
            TeachingAssignment.subject_id == subject.id,
            SchoolClass.school_level == school_level
        ).all()

    class_teachers = {}
    class_hours = {}
    split_class_ids = set()
    for a in subject_assignments:
        if a.class_id not in class_teachers:
            class_teachers[a.class_id] = set()
        if a.teacher_id:
            class_teachers[a.class_id].add(a.teacher_id)
        if a.group_number is not None:
            split_class_ids.add(a.class_id)
        if a.class_id not in class_hours:
            class_hours[a.class_id] = a.hours_per_week

    classes_not_assigned = [c for c in classes if not class_teachers.get(c.id)]
    classes_split = [c for c in classes if c.id in split_class_ids]

    attached_teacher_ids = db.session.query(TeachingAssignment.teacher_id)\
        .filter(
            TeachingAssignment.subject_id == subject.id,
            TeachingAssignment.teacher_id.isnot(None)
        ).distinct().all()
    attached_teacher_ids = [t[0] for t in attached_teacher_ids]

    attached_teachers = Teacher.query.filter(Teacher.id.in_(attached_teacher_ids))\
        .order_by(Teacher.full_name).all() if attached_teacher_ids else []

    all_teachers = Teacher.query.order_by(Teacher.full_name).all()

    return render_template('subjects/assignments.html',
                           subject=subject,
                           classes=classes,
                           class_teachers=class_teachers,
                           class_hours=class_hours,
                           classes_not_assigned=classes_not_assigned,
                           classes_split=classes_split,
                           attached_teachers=attached_teachers,
                           all_teachers=all_teachers,
                           school_level=school_level)


@subjects_bp.route('/<int:id>/save-assignments', methods=['POST'])
def save_assignments(id):
    """Save teacher-class assignments with auto group split/merge"""
    subject = Subject.query.get_or_404(id)
    school_level = request.form.get('school_level', 'elementary')

    teacher_ids = request.form.getlist('teacher_ids')
    teacher_ids = [int(tid) for tid in teacher_ids if tid]

    class_ids = db.session.query(TeachingAssignment.class_id)\
        .join(SchoolClass)\
        .filter(
            TeachingAssignment.subject_id == subject.id,
            SchoolClass.school_level == school_level
        ).distinct().all()
    class_ids = [c[0] for c in class_ids]

    classes = SchoolClass.query.filter(SchoolClass.id.in_(class_ids)).all() if class_ids else []

    for school_class in classes:
        checked_teachers = [
            tid for tid in teacher_ids
            if request.form.get(f't{tid}_c{school_class.id}')
        ]

        if len(checked_teachers) > 2:
            flash(f'Класс {school_class.name}: максимум 2 учителя на один предмет', 'danger')
            return redirect(url_for('subjects.assignments', id=subject.id, school_level=school_level))

        existing = TeachingAssignment.query.filter_by(
            subject_id=subject.id,
            class_id=school_class.id
        ).order_by(TeachingAssignment.group_number).all()

        if not existing:
            continue

        hours = existing[0].hours_per_week

        if len(checked_teachers) == 0:
            for i, a in enumerate(existing):
                if i == 0:
                    a.teacher_id = None
                    a.group_number = None
                else:
                    _reassign_cells_and_delete_assignment(a, existing[0].id)

        elif len(checked_teachers) == 1:
            for i, a in enumerate(existing):
                if i == 0:
                    a.teacher_id = checked_teachers[0]
                    a.group_number = None
                else:
                    _reassign_cells_and_delete_assignment(a, existing[0].id)

        elif len(checked_teachers) == 2:
            if len(existing) >= 2:
                existing[0].teacher_id = checked_teachers[0]
                existing[0].group_number = 1
                existing[1].teacher_id = checked_teachers[1]
                existing[1].group_number = 2
                for a in existing[2:]:
                    _reassign_cells_and_delete_assignment(a, existing[0].id)
            else:
                existing[0].teacher_id = checked_teachers[0]
                existing[0].group_number = 1
                db.session.add(TeachingAssignment(
                    subject_id=subject.id,
                    class_id=school_class.id,
                    teacher_id=checked_teachers[1],
                    hours_per_week=hours,
                    group_number=2
                ))

    db.session.commit()
    flash('Назначения сохранены', 'success')
    return redirect(url_for('subjects.assignments', id=subject.id, school_level=school_level))
