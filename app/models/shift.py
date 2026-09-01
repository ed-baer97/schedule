"""Shift model."""
from sqlalchemy import Column, ForeignKey, Integer, String, Time
from sqlalchemy.orm import relationship

from app.db import Base
from app.domain.school_level import level_label


class Shift(Base):
    __tablename__ = "shifts"

    id = Column(Integer, primary_key=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    name = Column(String(50), nullable=False)
    school_level = Column(String(20), nullable=False)
    start_lesson = Column(Integer, default=1)
    lessons_count = Column(Integer, default=6)
    working_days = Column(Integer, default=5)
    max_lessons_per_day = Column(Integer, default=7)
    class_hour_day = Column(Integer, nullable=True)
    class_hour_start = Column(Time, nullable=True)
    class_hour_end = Column(Time, nullable=True)
    class_hour_lessons_count = Column(Integer, nullable=True)

    school = relationship("School")
    classes = relationship("SchoolClass", back_populates="shift", lazy="dynamic")
    lesson_times = relationship(
        "ShiftLessonTime",
        back_populates="shift",
        lazy="dynamic",
        cascade="all, delete-orphan",
        order_by="ShiftLessonTime.day_of_week, ShiftLessonTime.lesson_number",
    )

    def __repr__(self):
        return f"<Shift {self.name}>"

    @property
    def school_level_display(self):
        return level_label(self.school_level)
