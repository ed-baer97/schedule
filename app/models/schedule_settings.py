"""
Schedule Settings model
"""
from app import db


class ScheduleSettings(db.Model):
    """Schedule settings for school level"""
    __tablename__ = 'schedule_settings'

    id = db.Column(db.Integer, primary_key=True)
    school_level = db.Column(db.String(20), nullable=False, unique=True)  # 'elementary' or 'secondary'
    max_lessons_per_subject_per_day = db.Column(db.Integer, default=2)  # Max 1 or 2 lessons of same subject per day
    classroom_mode = db.Column(db.String(20), default='class_room')  # 'teacher_room' | 'class_room'
    elementary_group_subjects_leave = db.Column(db.Boolean, default=True)  # групповые уроки: дети уходят к учителю

    def __repr__(self):
        return f'<ScheduleSettings {self.school_level}>'
