"""
Teacher model
"""
from datetime import datetime
from app import db


class Teacher(db.Model):
    """Teacher entity"""
    __tablename__ = 'teachers'

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    home_classroom_id = db.Column(db.Integer, db.ForeignKey('classrooms.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    assignments = db.relationship('TeachingAssignment', back_populates='teacher', lazy='dynamic')
    home_classroom = db.relationship('Classroom', foreign_keys=[home_classroom_id])

    def __repr__(self):
        return f'<Teacher {self.full_name}>'

    @property
    def display_name(self):
        return self.full_name
