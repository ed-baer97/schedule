"""Schedule cell model."""
from sqlalchemy import Column, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import relationship

from app.db import Base


class ScheduleCell(Base):
    __tablename__ = "schedule_cells"

    id = Column(Integer, primary_key=True)
    class_id = Column(Integer, ForeignKey("school_classes.id"), nullable=False)
    day_of_week = Column(Integer, nullable=False)
    lesson_number = Column(Integer, nullable=False)
    assignment_id = Column(Integer, ForeignKey("teaching_assignments.id"), nullable=False)
    classroom_id = Column(Integer, ForeignKey("classrooms.id"), nullable=True)

    school_class = relationship("SchoolClass", back_populates="schedule_cells")
    assignment = relationship("TeachingAssignment", back_populates="schedule_cells")
    classroom = relationship("Classroom", back_populates="schedule_cells")

    __table_args__ = (
        UniqueConstraint(
            "class_id",
            "day_of_week",
            "lesson_number",
            "assignment_id",
            name="uq_schedule_cell",
        ),
    )

    def __repr__(self):
        return (
            f"<ScheduleCell {self.school_class.name} "
            f"Day{self.day_of_week} Lesson{self.lesson_number}>"
        )

    @property
    def subject(self):
        return self.assignment.subject

    @property
    def teacher(self):
        return self.assignment.teacher
