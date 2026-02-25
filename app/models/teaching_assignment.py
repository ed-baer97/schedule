"""
Teaching Assignment model
"""
from app import db


class TeachingAssignment(db.Model):
    """Teaching assignment: links subject, teacher, and class"""
    __tablename__ = 'teaching_assignments'

    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=True)  # Can be null initially
    class_id = db.Column(db.Integer, db.ForeignKey('school_classes.id'), nullable=False)
    hours_per_week = db.Column(db.Integer, nullable=False)
    group_number = db.Column(db.Integer, nullable=True)  # None = whole class, 1 or 2 = subgroup
    preferred_classroom_id = db.Column(db.Integer, db.ForeignKey('classrooms.id'), nullable=True)

    # Relationships
    subject = db.relationship('Subject', back_populates='assignments')
    teacher = db.relationship('Teacher', back_populates='assignments')
    school_class = db.relationship('SchoolClass', back_populates='assignments')
    preferred_classroom = db.relationship('Classroom')
    schedule_cells = db.relationship('ScheduleCell', back_populates='assignment', lazy='dynamic')

    def __repr__(self):
        return f'<TeachingAssignment {self.subject.name} - {self.school_class.name}>'

    @property
    def is_group_subject(self):
        """Check if subject is split into groups"""
        return self.group_number is not None

    @property
    def scheduled_hours(self):
        """Count of already scheduled lessons"""
        return self.schedule_cells.count()

    @property
    def remaining_hours(self):
        """Hours still to be scheduled"""
        return self.hours_per_week - self.scheduled_hours

    @property
    def display_name(self):
        """Display name for the assignment"""
        name = self.subject.display_name
        if self.group_number:
            name += f' (гр.{self.group_number})'
        return name
