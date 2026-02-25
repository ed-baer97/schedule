"""
Reports and export routes
"""
import io
from flask import Blueprint, render_template, request, make_response, send_file
from app.models import SchoolClass, Teacher, Shift, ScheduleCell, TeachingAssignment, ScheduleSettings
import pandas as pd

reports_bp = Blueprint('reports', __name__)


@reports_bp.route('/')
def index():
    """Reports page"""
    teachers = Teacher.query.order_by(Teacher.full_name).all()
    classes = SchoolClass.query.order_by(SchoolClass.grade, SchoolClass.name).all()
    shifts = Shift.query.all()
    
    return render_template('reports/index.html',
                         teachers=teachers,
                         classes=classes,
                         shifts=shifts)


@reports_bp.route('/class/<int:class_id>')
def class_schedule(class_id):
    """Schedule for a specific class"""
    school_class = SchoolClass.query.get_or_404(class_id)
    
    settings = ScheduleSettings.query.filter_by(school_level=school_class.school_level).first()
    working_days = settings.working_days if settings else 5
    max_lessons = settings.max_lessons_per_day if settings else 7
    
    cells = ScheduleCell.query.filter_by(class_id=class_id).all()
    
    # Build schedule matrix
    schedule = {}
    for cell in cells:
        key = (cell.day_of_week, cell.lesson_number)
        if key not in schedule:
            schedule[key] = []
        schedule[key].append(cell)
    
    day_names = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']
    
    return render_template('reports/class_schedule.html',
                         school_class=school_class,
                         schedule=schedule,
                         working_days=working_days,
                         max_lessons=max_lessons,
                         day_names=day_names)


@reports_bp.route('/teacher/<int:teacher_id>')
def teacher_schedule(teacher_id):
    """Schedule for a specific teacher"""
    teacher = Teacher.query.get_or_404(teacher_id)
    
    # Get all cells for this teacher
    cells = ScheduleCell.query.join(TeachingAssignment).filter(
        TeachingAssignment.teacher_id == teacher_id
    ).all()
    
    # Build schedule matrix
    schedule = {}
    for cell in cells:
        key = (cell.day_of_week, cell.lesson_number)
        if key not in schedule:
            schedule[key] = []
        schedule[key].append(cell)
    
    day_names = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']
    
    return render_template('reports/teacher_schedule.html',
                         teacher=teacher,
                         schedule=schedule,
                         working_days=6,
                         max_lessons=8,
                         day_names=day_names)


@reports_bp.route('/export/class/<int:class_id>')
def export_class_excel(class_id):
    """Export class schedule to Excel"""
    school_class = SchoolClass.query.get_or_404(class_id)
    
    settings = ScheduleSettings.query.filter_by(school_level=school_class.school_level).first()
    working_days = settings.working_days if settings else 5
    max_lessons = settings.max_lessons_per_day if settings else 7
    
    cells = ScheduleCell.query.filter_by(class_id=class_id).all()
    
    day_names = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']
    
    # Build DataFrame
    data = []
    for day in range(1, working_days + 1):
        for lesson in range(1, max_lessons + 1):
            row = {'День': day_names[day - 1], 'Урок': lesson}
            
            matching_cells = [c for c in cells if c.day_of_week == day and c.lesson_number == lesson]
            
            if matching_cells:
                subjects = []
                teachers = []
                rooms = []
                for cell in matching_cells:
                    subjects.append(cell.subject.display_name)
                    teachers.append(cell.teacher.display_name if cell.teacher else '—')
                    rooms.append(cell.classroom.number if cell.classroom else '—')
                
                row['Предмет'] = ' / '.join(subjects)
                row['Учитель'] = ' / '.join(teachers)
                row['Кабинет'] = ' / '.join(rooms)
            else:
                row['Предмет'] = ''
                row['Учитель'] = ''
                row['Кабинет'] = ''
            
            data.append(row)
    
    df = pd.DataFrame(data)
    
    # Create Excel file
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name=f'Расписание {school_class.name}', index=False)
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'расписание_{school_class.name}.xlsx'
    )


@reports_bp.route('/export/teacher/<int:teacher_id>')
def export_teacher_excel(teacher_id):
    """Export teacher schedule to Excel"""
    teacher = Teacher.query.get_or_404(teacher_id)
    
    cells = ScheduleCell.query.join(TeachingAssignment).filter(
        TeachingAssignment.teacher_id == teacher_id
    ).all()
    
    day_names = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']
    
    # Build DataFrame
    data = []
    for day in range(1, 7):
        for lesson in range(1, 9):
            row = {'День': day_names[day - 1], 'Урок': lesson}
            
            matching_cells = [c for c in cells if c.day_of_week == day and c.lesson_number == lesson]
            
            if matching_cells:
                classes = []
                subjects = []
                rooms = []
                for cell in matching_cells:
                    classes.append(cell.school_class.name)
                    subjects.append(cell.subject.display_name)
                    rooms.append(cell.classroom.number if cell.classroom else '—')
                
                row['Класс'] = ' / '.join(classes)
                row['Предмет'] = ' / '.join(subjects)
                row['Кабинет'] = ' / '.join(rooms)
            else:
                row['Класс'] = ''
                row['Предмет'] = ''
                row['Кабинет'] = ''
            
            data.append(row)
    
    df = pd.DataFrame(data)
    
    # Create Excel file
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name=f'Расписание {teacher.full_name}'[:31], index=False)
    output.seek(0)
    
    filename = teacher.full_name
    filename = filename.replace(' ', '_').replace('.', '')
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'расписание_{filename}.xlsx'
    )


@reports_bp.route('/export/all/<school_level>')
def export_all_excel(school_level):
    """Export full schedule for school level"""
    if school_level not in ['elementary', 'secondary']:
        school_level = 'elementary'
    
    classes = SchoolClass.query.filter_by(school_level=school_level)\
        .order_by(SchoolClass.grade, SchoolClass.name).all()
    
    settings = ScheduleSettings.query.filter_by(school_level=school_level).first()
    working_days = settings.working_days if settings else 5
    max_lessons = settings.max_lessons_per_day if settings else 7
    
    day_names = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб']
    
    # Build full schedule matrix
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for day in range(1, working_days + 1):
            data = {'Урок': list(range(1, max_lessons + 1))}
            
            for school_class in classes:
                cells = ScheduleCell.query.filter_by(
                    class_id=school_class.id,
                    day_of_week=day
                ).all()
                
                column_data = []
                for lesson in range(1, max_lessons + 1):
                    matching = [c for c in cells if c.lesson_number == lesson]
                    if matching:
                        cell_text = []
                        for c in matching:
                            text = c.subject.name
                            if c.assignment.group_number:
                                text += f'(гр.{c.assignment.group_number})'
                            cell_text.append(text)
                        column_data.append('\n'.join(cell_text))
                    else:
                        column_data.append('')
                
                data[school_class.name] = column_data
            
            df = pd.DataFrame(data)
            df.to_excel(writer, sheet_name=day_names[day - 1], index=False)
    
    output.seek(0)
    
    level_name = 'начальная' if school_level == 'elementary' else 'основная'
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'расписание_{level_name}_школа.xlsx'
    )
