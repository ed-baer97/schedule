"""Background job status (auto-schedule etc.)."""
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db import Base

JOB_PENDING = "pending"
JOB_RUNNING = "running"
JOB_DONE = "done"
JOB_FAILED = "failed"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    kind = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default=JOB_PENDING, index=True)
    progress = Column(Text, nullable=True)  # JSON blob
    result = Column(Text, nullable=True)  # JSON blob
    error = Column(Text, nullable=True)
    celery_task_id = Column(String(64), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=_utc_now)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now)

    school = relationship("School")
    created_by = relationship("User")
