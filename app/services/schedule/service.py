"""ScheduleService composed from query/command mixins."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain.schedule_variant import KIND_MAIN, InvalidScheduleVariant, normalize_variant
from app.services.errors import BadRequestError
from app.services.schedule.commands import ScheduleCommandsMixin
from app.services.schedule.queries import ScheduleQueriesMixin
from app.services.validators import ScheduleValidator


class ScheduleService(ScheduleQueriesMixin, ScheduleCommandsMixin):
    def __init__(self, db: Session, school_id: int):
        self.db = db
        self.school_id = school_id
        self.schedule_kind = KIND_MAIN
        self.week_index = 0
        self.validator = ScheduleValidator(db, school_id=school_id)

    def set_variant(
        self, kind: str | None = None, week: int | None = None
    ) -> "ScheduleService":
        try:
            self.schedule_kind, self.week_index = normalize_variant(kind, week)
        except InvalidScheduleVariant as exc:
            raise BadRequestError(str(exc)) from exc
        self.validator = ScheduleValidator(
            self.db,
            school_id=self.school_id,
            schedule_kind=self.schedule_kind,
            week_index=self.week_index,
        )
        return self


class ScheduleService(ScheduleQueriesMixin, ScheduleCommandsMixin):
    def __init__(self, db: Session, school_id: int):
        self.db = db
        self.school_id = school_id
        self.schedule_kind = KIND_MAIN
        self.week_index = 0
        self.validator = ScheduleValidator(db, school_id=school_id)

    def set_variant(
        self, kind: str | None = None, week: int | None = None
    ) -> "ScheduleService":
        self.schedule_kind, self.week_index = normalize_variant(kind, week)
        self.validator = ScheduleValidator(
            self.db,
            school_id=self.school_id,
            schedule_kind=self.schedule_kind,
            week_index=self.week_index,
        )
        return self
