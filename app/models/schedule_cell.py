"""
Schedule Cell model
"""
from app import db


class ScheduleCell(db.Model):
    """Single lesson in the schedule"""
    __tablename__ = 'schedule_cells'

    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('school_classes.id'), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)  # 1-6 (Mon-Sat)
    lesson_number = db.Column(db.Integer, nullable=False)  # Lesson number
    assignment_id = db.Column(db.Integer, db.ForeignKey('teaching_assignments.id'), nullable=False)
    classroom_id = db.Column(db.Integer, db.ForeignKey('classrooms.id'), nullable=True)

    # Relationships
    school_class = db.relationship('SchoolClass', back_populates='schedule_cells')
    assignment = db.relationship('TeachingAssignment', back_populates='schedule_cells')
    classroom = db.relationship('Classroom', back_populates='schedule_cells')

    # Unique constraint: same class, day, lesson, assignment can appear only once
    __table_args__ = (
        db.UniqueConstraint('class_id', 'day_of_week', 'lesson_number', 'assignment_id', 
                           name='uq_schedule_cell'),
    )

    def __repr__(self):
        return f'<ScheduleCell {self.school_class.name} Day{self.day_of_week} Lesson{self.lesson_number}>'

    @property
    def subject(self):
        """Get subject from assignment"""
        return self.assignment.subject

    @property
    def teacher(self):
        """Get teacher from assignment"""
        return self.assignment.teacher
