"""
School Class model
"""
from app import db


class SchoolClass(db.Model):
    """School class entity (1A, 5B, etc.)"""
    __tablename__ = 'school_classes'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(10), nullable=False)  # "1А", "5Б", "11В"
    grade = db.Column(db.Integer, nullable=False)  # Class number (1-11)
    school_level = db.Column(db.String(20), nullable=False)  # 'elementary' or 'secondary'
    shift_id = db.Column(db.Integer, db.ForeignKey('shifts.id'))
    students_count = db.Column(db.Integer)
    home_classroom_id = db.Column(db.Integer, db.ForeignKey('classrooms.id'), nullable=True)

    # Relationships
    shift = db.relationship('Shift', back_populates='classes')
    home_classroom = db.relationship('Classroom', foreign_keys=[home_classroom_id])
    assignments = db.relationship('TeachingAssignment', back_populates='school_class', lazy='dynamic')
    schedule_cells = db.relationship('ScheduleCell', back_populates='school_class', lazy='dynamic')

    def __repr__(self):
        return f'<SchoolClass {self.name}>'

    @property
    def school_level_display(self):
        """Human-readable school level"""
        return 'Начальная школа' if self.school_level == 'elementary' else 'Основная школа'
