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

    # Relationships
    classes = db.relationship('SchoolClass', back_populates='shift', lazy='dynamic')

    def __repr__(self):
        return f'<Shift {self.name}>'

    @property
    def school_level_display(self):
        """Human-readable school level"""
        return 'Начальная школа' if self.school_level == 'elementary' else 'Основная школа'
