"""Teacher model."""
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.db import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Teacher(Base):
    __tablename__ = "teachers"

    id = Column(Integer, primary_key=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    full_name = Column(String(200), nullable=False)
    email = Column(String(100))
    phone = Column(String(20))
    home_classroom_id = Column(Integer, ForeignKey("classrooms.id"), nullable=True)
    created_at = Column(DateTime, default=_utc_now)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now)

    school = relationship("School")
    assignments = relationship("TeachingAssignment", back_populates="teacher", lazy="dynamic")
    home_classroom = relationship(
        "Classroom",
        foreign_keys=[home_classroom_id],
        back_populates="teachers",
    )

    def __repr__(self):
        return f"<Teacher {self.full_name}>"

    @property
    def display_name(self):
        return self.full_name
