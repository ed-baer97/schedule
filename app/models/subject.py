"""Subject model."""
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.db import Base


class Subject(Base):
    __tablename__ = "subjects"

    DEFAULT_COLOR = "#147f78"
    COLOR_PALETTE = (
        "#147f78", "#c45a42", "#c4842e", "#0e5c57", "#3f5248",
        "#1a6a64", "#a65a48", "#8b6b3e", "#2a403a", "#b86b2e",
        "#4a7c78", "#7a4a3a", "#5b6b4a", "#3d5a6b", "#6b5340",
    )
    _LEGACY_COLOR_MAP = {
        "#3498db": "#147f78",
        "#e74c3c": "#c45a42",
        "#27ae60": "#5b6b4a",
        "#f39c12": "#c4842e",
        "#9b59b6": "#3d5a6b",
        "#1abc9c": "#1a6a64",
        "#e67e22": "#b86b2e",
        "#34495e": "#2a403a",
        "#16a085": "#0e5c57",
        "#c0392b": "#a65a48",
        "#2980b9": "#4a7c78",
        "#8e44ad": "#3d5a6b",
        "#2ecc71": "#5b6b4a",
        "#d35400": "#8b6b3e",
        "#7f8c8d": "#3f5248",
    }

    id = Column(Integer, primary_key=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    color = Column(String(7), default=DEFAULT_COLOR)
    requires_fixed_classroom = Column(Boolean, default=False)

    school = relationship("School")
    assignments = relationship("TeachingAssignment", back_populates="subject", lazy="dynamic")
    classrooms = relationship(
        "Classroom",
        secondary="classroom_subjects",
        back_populates="subjects",
        lazy="select",
    )

    def __repr__(self):
        return f"<Subject {self.name}>"

    @property
    def display_name(self):
        return self.name

    @property
    def display_color(self):
        raw = (self.color or self.DEFAULT_COLOR).lower()
        return self._LEGACY_COLOR_MAP.get(raw, self.color or self.DEFAULT_COLOR)
