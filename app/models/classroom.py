"""Classroom model."""
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.db import Base


class Classroom(Base):
    __tablename__ = "classrooms"

    id = Column(Integer, primary_key=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    number = Column(String(20), nullable=False)
    name = Column(String(100))
    capacity = Column(Integer)
    classes_capacity = Column(Integer, default=1)
    floor = Column(Integer)
    building = Column(String(50))
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=True, index=True)
    is_exclusive = Column(Boolean, default=False, nullable=False)

    school = relationship("School")
    subject = relationship("Subject", foreign_keys=[subject_id], lazy="select")
    teachers = relationship(
        "Teacher",
        back_populates="home_classroom",
        foreign_keys="[Teacher.home_classroom_id]",
        order_by="Teacher.full_name",
    )
    schedule_cells = relationship("ScheduleCell", back_populates="classroom", lazy="dynamic")

    def __repr__(self):
        return f"<Classroom {self.number}>"

    @property
    def display_name(self):
        if self.name:
            return f"{self.number} ({self.name})"
        return self.number
