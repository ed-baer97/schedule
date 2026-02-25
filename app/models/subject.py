"""
Subject model
"""
from app import db


class Subject(db.Model):
    """School subject entity"""
    __tablename__ = 'subjects'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    color = db.Column(db.String(7), default='#3498db')  # Display color (#RRGGBB)
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
