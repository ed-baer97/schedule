"""
Subject model
"""
from app import db


class Subject(db.Model):
    """School subject entity"""
    __tablename__ = 'subjects'

    DEFAULT_COLOR = '#3498db'
    # Стандартная палитра; любой другой оттенок — через «Свой цвет» (системный диалог)
    COLOR_PALETTE = (
        '#3498db', '#e74c3c', '#27ae60', '#f39c12', '#9b59b6',
        '#1abc9c', '#e67e22', '#34495e', '#16a085', '#c0392b',
        '#2980b9', '#8e44ad', '#2ecc71', '#d35400', '#7f8c8d',
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    color = db.Column(db.String(7), default=DEFAULT_COLOR)  # Display color (#RRGGBB)
    requires_fixed_classroom = db.Column(db.Boolean, default=False)  # Информатика, Физкультура, Технология
    default_classroom_id = db.Column(db.Integer, db.ForeignKey('classrooms.id'), nullable=True)

    # Relationships
    assignments = db.relationship('TeachingAssignment', back_populates='subject', lazy='dynamic')
    default_classroom = db.relationship('Classroom', foreign_keys=[default_classroom_id], lazy='select')

    def __repr__(self):
        return f'<Subject {self.name}>'

    @property
    def display_name(self):
        return self.name

    @property
    def display_color(self):
        """Для отображения: в БД могут быть старые записи с color=NULL."""
        return self.color if self.color else self.DEFAULT_COLOR
