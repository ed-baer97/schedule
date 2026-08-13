"""
Shift model
"""
from app import db


class Shift(db.Model):
    """School shift entity"""
    __tablename__ = 'shifts'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)  # "1 смена", "2 смена"
    school_level = db.Column(db.String(20), nullable=False)  # 'elementary' or 'secondary'
    start_lesson = db.Column(db.Integer, default=1)  # Starting lesson number
    lessons_count = db.Column(db.Integer, default=6)  # Number of lessons in shift
    working_days = db.Column(db.Integer, default=5)  # 5 (Пн–Пт) или 6 (Пн–Сб)
    max_lessons_per_day = db.Column(db.Integer, default=7)  # Сетка дня: номера уроков 1..N
    # Классный час: один раз в неделю (день 1–6) и интервал времени
    class_hour_day = db.Column(db.Integer, nullable=True)  # 1=Пн … 6=Сб; None = нет
    class_hour_start = db.Column(db.Time, nullable=True)
    class_hour_end = db.Column(db.Time, nullable=True)

    # Relationships
    classes = db.relationship('SchoolClass', back_populates='shift', lazy='dynamic')
    lesson_times = db.relationship(
        'ShiftLessonTime', back_populates='shift', lazy='dynamic',
        cascade='all, delete-orphan',
        order_by='ShiftLessonTime.day_of_week, ShiftLessonTime.lesson_number',
    )

    def __repr__(self):
        return f'<Shift {self.name}>'

    @property
    def school_level_display(self):
        """Human-readable school level"""
        return 'Начальная школа' if self.school_level == 'elementary' else 'Основная школа'
