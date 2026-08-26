"""Classroom model."""
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Table
from sqlalchemy.orm import relationship

from app.db import Base


classroom_subjects = Table(
    "classroom_subjects",
    Base.metadata,
    Column(
        "classroom_id",
        Integer,
        ForeignKey("classrooms.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "subject_id",
        Integer,
        ForeignKey("subjects.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


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
    is_exclusive = Column(Boolean, default=False, nullable=False)

    school = relationship("School")
    subjects = relationship(
        "Subject",
        secondary=classroom_subjects,
        back_populates="classrooms",
        lazy="selectin",
    )
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
