"""Schedule settings model."""
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.db import Base


class ScheduleSettings(Base):
    __tablename__ = "schedule_settings"

    id = Column(Integer, primary_key=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    school_level = Column(String(20), nullable=False)
    max_lessons_per_subject_per_day = Column(Integer, default=2)
    classroom_mode = Column(String(20), default="class_room")
    elementary_group_subjects_leave = Column(Boolean, default=True)

    school = relationship("School")

    __table_args__ = (
        UniqueConstraint("school_id", "school_level", name="uq_schedule_settings_school_level"),
    )

    def __repr__(self):
        return f"<ScheduleSettings {self.school_level}>"
