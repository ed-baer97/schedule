"""
Bell schedule: start/end time per lesson number for a shift
"""
from app import db


class ShiftLessonTime(db.Model):
    __tablename__ = 'shift_lesson_times'

    id = db.Column(db.Integer, primary_key=True)
    shift_id = db.Column(db.Integer, db.ForeignKey('shifts.id', ondelete='CASCADE'), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)  # 1=Пн … 6=Сб
    lesson_number = db.Column(db.Integer, nullable=False)
    time_start = db.Column(db.Time, nullable=False)
    time_end = db.Column(db.Time, nullable=False)

    shift = db.relationship('Shift', back_populates='lesson_times')

    __table_args__ = (
        db.UniqueConstraint('shift_id', 'lesson_number', 'day_of_week', name='uq_shift_lesson_day'),
    )

    def __repr__(self):
        return f'<ShiftLessonTime shift={self.shift_id} L{self.lesson_number}>'
