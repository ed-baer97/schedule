"""Schedule settings model."""
from sqlalchemy import Boolean, Column, Integer, String

from app.db import Base


class ScheduleSettings(Base):
    __tablename__ = "schedule_settings"

    id = Column(Integer, primary_key=True)
    school_level = Column(String(20), nullable=False, unique=True)
    max_lessons_per_subject_per_day = Column(Integer, default=2)
    classroom_mode = Column(String(20), default="class_room")
    elementary_group_subjects_leave = Column(Boolean, default=True)

    def __repr__(self):
        return f"<ScheduleSettings {self.school_level}>"
