"""ScheduleService composed from query/command mixins."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.schedule.commands import ScheduleCommandsMixin
from app.services.schedule.queries import ScheduleQueriesMixin
from app.services.validators import ScheduleValidator


class ScheduleService(ScheduleQueriesMixin, ScheduleCommandsMixin):
    def __init__(self, db: Session, school_id: int):
        self.db = db
        self.school_id = school_id
        self.validator = ScheduleValidator(db, school_id=school_id)
