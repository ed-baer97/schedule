"""School class model."""
from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.db import Base


class SchoolClass(Base):
    __tablename__ = "school_classes"

    id = Column(Integer, primary_key=True)
    name = Column(String(10), nullable=False)
    grade = Column(Integer, nullable=False)
    school_level = Column(String(20), nullable=False)
    shift_id = Column(Integer, ForeignKey("shifts.id"))
    students_count = Column(Integer)
    home_classroom_id = Column(Integer, ForeignKey("classrooms.id"), nullable=True)

    shift = relationship("Shift", back_populates="classes")
    home_classroom = relationship("Classroom", foreign_keys=[home_classroom_id])
    assignments = relationship("TeachingAssignment", back_populates="school_class", lazy="dynamic")
    schedule_cells = relationship("ScheduleCell", back_populates="school_class", lazy="dynamic")

    def __repr__(self):
        return f"<SchoolClass {self.name}>"

    @property
    def school_level_display(self):
        return "Начальная школа" if self.school_level == "elementary" else "Основная школа"
