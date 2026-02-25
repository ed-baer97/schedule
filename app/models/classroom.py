"""
Classroom model
"""
from app import db


class Classroom(db.Model):
    """Classroom/Room entity"""
    __tablename__ = 'classrooms'

    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(20), nullable=False)  # Room number
    name = db.Column(db.String(100))  # Room name (Physics, Gym, etc.)
    capacity = db.Column(db.Integer)  # Student capacity
    classes_capacity = db.Column(db.Integer, default=1)  # Max classes per slot (1 = обычный кабинет, 2+ = спортзал и т.п.)
    floor = db.Column(db.Integer)
    building = db.Column(db.String(50))  # Building name

    # Relationships
    schedule_cells = db.relationship('ScheduleCell', back_populates='classroom', lazy='dynamic')

    def __repr__(self):
        return f'<Classroom {self.number}>'

    @property
    def display_name(self):
        """Return formatted room display"""
        if self.name:
            return f'{self.number} ({self.name})'
        return self.number
