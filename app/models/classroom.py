"""Classroom model."""
from sqlalchemy import Column, ForeignKey, Integer, String
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

    school = relationship("School")
    schedule_cells = relationship("ScheduleCell", back_populates="classroom", lazy="dynamic")

    def __repr__(self):
        return f"<Classroom {self.number}>"

    @property
    def display_name(self):
        if self.name:
            return f"{self.number} ({self.name})"
        return self.number
