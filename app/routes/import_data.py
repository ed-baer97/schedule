"""
Excel import routes
"""
import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, current_app
from werkzeug.utils import secure_filename
from app import db
from app.services.excel_import import ExcelImporter

import_bp = Blueprint('import', __name__)

ALLOWED_EXTENSIONS = {'xlsx', 'xls'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@import_bp.route('/')
def index():
    """Import page"""
    return render_template('import/index.html')


@import_bp.route('/teachers', methods=['POST'])
def import_teachers():
    """Import teachers from Excel"""
    if 'file' not in request.files:
        flash('Файл не выбран', 'danger')
        return redirect(url_for('import.index'))
    
    file = request.files['file']
    if file.filename == '':
        flash('Файл не выбран', 'danger')
        return redirect(url_for('import.index'))
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        upload_folder = current_app.config['UPLOAD_FOLDER']
        os.makedirs(upload_folder, exist_ok=True)
        filepath = os.path.join(upload_folder, filename)
        file.save(filepath)
        
        try:
            importer = ExcelImporter()
            count = importer.import_teachers(filepath)
            flash(f'Импортировано учителей: {count}', 'success')
        except Exception as e:
            flash(f'Ошибка импорта: {str(e)}', 'danger')
        finally:
            os.remove(filepath)
        
        return redirect(url_for('import.index'))
    
    flash('Неверный формат файла. Используйте .xlsx или .xls', 'danger')
    return redirect(url_for('import.index'))


@import_bp.route('/classrooms', methods=['POST'])
def import_classrooms():
    """Import classrooms from Excel"""
    if 'file' not in request.files:
        flash('Файл не выбран', 'danger')
        return redirect(url_for('import.index'))

    file = request.files['file']
    if file.filename == '':
        flash('Файл не выбран', 'danger')
        return redirect(url_for('import.index'))

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        upload_folder = current_app.config['UPLOAD_FOLDER']
        os.makedirs(upload_folder, exist_ok=True)
        filepath = os.path.join(upload_folder, filename)
        file.save(filepath)

        try:
            importer = ExcelImporter()
            count = importer.import_classrooms(filepath)
            flash(f'Импортировано кабинетов: {count}', 'success')
        except Exception as e:
            flash(f'Ошибка импорта: {str(e)}', 'danger')
        finally:
            os.remove(filepath)

        return redirect(url_for('import.index'))

    flash('Неверный формат файла. Используйте .xlsx или .xls', 'danger')
    return redirect(url_for('import.index'))


@import_bp.route('/curriculum/<school_level>', methods=['POST'])
def import_curriculum(school_level):
    """Import curriculum (subjects x classes) from Excel"""
    if school_level not in ['elementary', 'secondary']:
        flash('Неверный уровень школы', 'danger')
        return redirect(url_for('import.index'))
    
    if 'file' not in request.files:
        flash('Файл не выбран', 'danger')
        return redirect(url_for('import.index'))
    
    file = request.files['file']
    if file.filename == '':
        flash('Файл не выбран', 'danger')
        return redirect(url_for('import.index'))
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        upload_folder = current_app.config['UPLOAD_FOLDER']
        os.makedirs(upload_folder, exist_ok=True)
        filepath = os.path.join(upload_folder, filename)
        file.save(filepath)
        
        try:
            importer = ExcelImporter()
            subjects_count, assignments_count = importer.import_curriculum(filepath, school_level)
            flash(f'Импортировано предметов: {subjects_count}, записей нагрузки: {assignments_count}', 'success')
        except Exception as e:
            flash(f'Ошибка импорта: {str(e)}', 'danger')
        finally:
            os.remove(filepath)
        
        return redirect(url_for('import.index'))
    
    flash('Неверный формат файла. Используйте .xlsx или .xls', 'danger')
    return redirect(url_for('import.index'))


@import_bp.route('/template/<template_type>')
def download_template(template_type):
    """Download Excel template"""
    templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'excel_templates')
    
    if template_type == 'teachers':
        filepath = os.path.join(templates_dir, 'teachers_template.xlsx')
        filename = 'шаблон_учителя.xlsx'
    elif template_type == 'curriculum':
        filepath = os.path.join(templates_dir, 'curriculum_template.xlsx')
        filename = 'шаблон_учебный_план.xlsx'
    elif template_type == 'classrooms':
        filepath = os.path.join(templates_dir, 'classrooms_template.xlsx')
        filename = 'шаблон_кабинеты.xlsx'
    else:
        flash('Неверный тип шаблона', 'danger')
        return redirect(url_for('import.index'))
    
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True, download_name=filename)
    else:
        flash('Шаблон не найден', 'danger')
        return redirect(url_for('import.index'))
