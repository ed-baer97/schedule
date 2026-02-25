"""
School Schedule Application
Flask app factory
"""
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

from app.config import Config

db = SQLAlchemy()
migrate = Migrate()


def create_app(config_class=Config):
    """Application factory pattern"""
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)

    from app.routes.main import main_bp
    from app.routes.teachers import teachers_bp
    from app.routes.classrooms import classrooms_bp
    from app.routes.classes import classes_bp
    from app.routes.shifts import shifts_bp
    from app.routes.subjects import subjects_bp
    from app.routes.assignments import assignments_bp
    from app.routes.workload import workload_bp
    from app.routes.schedule import schedule_bp
    from app.routes.import_data import import_bp
    from app.routes.reports import reports_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(assignments_bp, url_prefix='/assignments')
    app.register_blueprint(teachers_bp, url_prefix='/teachers')
    app.register_blueprint(classrooms_bp, url_prefix='/classrooms')
    app.register_blueprint(classes_bp, url_prefix='/classes')
    app.register_blueprint(shifts_bp, url_prefix='/shifts')
    app.register_blueprint(subjects_bp, url_prefix='/subjects')
    app.register_blueprint(workload_bp, url_prefix='/workload')
    app.register_blueprint(schedule_bp, url_prefix='/schedule')
    app.register_blueprint(import_bp, url_prefix='/import')
    app.register_blueprint(reports_bp, url_prefix='/reports')

    return app
