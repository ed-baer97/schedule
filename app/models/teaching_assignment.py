"""Teaching assignment model."""
from sqlalchemy import Column, ForeignKey, Integer
from sqlalchemy.orm import relationship

from app.db import Base


class TeachingAssignment(Base):
    __tablename__ = "teaching_assignments"

    id = Column(Integer, primary_key=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=True)
    class_id = Column(Integer, ForeignKey("school_classes.id"), nullable=False)
    hours_per_week = Column(Integer, nullable=False)
    group_number = Column(Integer, nullable=True)
    preferred_classroom_id = Column(Integer, ForeignKey("classrooms.id"), nullable=True)

    school = relationship("School")
    subject = relationship("Subject", back_populates="assignments")
    teacher = relationship("Teacher", back_populates="assignments")
    school_class = relationship("SchoolClass", back_populates="assignments")
    preferred_classroom = relationship("Classroom")
    schedule_cells = relationship("ScheduleCell", back_populates="assignment", lazy="dynamic")

    def __repr__(self):
        return f"<TeachingAssignment {self.subject.name} - {self.school_class.name}>"

    @property
    def is_group_subject(self):
        return self.group_number is not None

    @property
    def scheduled_hours(self):
        return self.schedule_cells.count()

    @property
    def remaining_hours(self):
        return self.hours_per_week - self.scheduled_hours

    @property
    def display_name(self):
        name = self.subject.display_name
        if self.group_number:
            name += f" (гр.{self.group_number})"
        return name
