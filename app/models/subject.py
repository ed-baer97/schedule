"""Subject model."""
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.db import Base


class Subject(Base):
    __tablename__ = "subjects"

    DEFAULT_COLOR = "#3498db"
    COLOR_PALETTE = (
        "#3498db", "#e74c3c", "#27ae60", "#f39c12", "#9b59b6",
        "#1abc9c", "#e67e22", "#34495e", "#16a085", "#c0392b",
        "#2980b9", "#8e44ad", "#2ecc71", "#d35400", "#7f8c8d",
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    color = Column(String(7), default=DEFAULT_COLOR)
    requires_fixed_classroom = Column(Boolean, default=False)
    default_classroom_id = Column(Integer, ForeignKey("classrooms.id"), nullable=True)

    assignments = relationship("TeachingAssignment", back_populates="subject", lazy="dynamic")
    default_classroom = relationship("Classroom", foreign_keys=[default_classroom_id], lazy="select")

    def __repr__(self):
        return f"<Subject {self.name}>"

    @property
    def display_name(self):
        return self.name

    @property
    def display_color(self):
        return self.color if self.color else self.DEFAULT_COLOR
