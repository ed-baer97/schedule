"""Bell schedule: start/end time per lesson number for a shift."""
from sqlalchemy import Column, ForeignKey, Integer, Time, UniqueConstraint
from sqlalchemy.orm import relationship

from app.db import Base


class ShiftLessonTime(Base):
    __tablename__ = "shift_lesson_times"

    id = Column(Integer, primary_key=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    shift_id = Column(Integer, ForeignKey("shifts.id", ondelete="CASCADE"), nullable=False)
    day_of_week = Column(Integer, nullable=False)
    lesson_number = Column(Integer, nullable=False)
    time_start = Column(Time, nullable=False)
    time_end = Column(Time, nullable=False)

    school = relationship("School")
    shift = relationship("Shift", back_populates="lesson_times")

    __table_args__ = (
        UniqueConstraint("shift_id", "lesson_number", "day_of_week", name="uq_shift_lesson_day"),
    )

    def __repr__(self):
        return f"<ShiftLessonTime shift={self.shift_id} L{self.lesson_number}>"
