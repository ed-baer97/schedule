"""Schedule grid variants: main weekly, temporary overlay, monthly 4-week."""
from __future__ import annotations

KIND_MAIN = "main"
KIND_TEMPORARY = "temporary"
KIND_MONTHLY = "monthly"

KINDS = (KIND_MAIN, KIND_TEMPORARY, KIND_MONTHLY)
MONTHLY_WEEKS = (1, 2, 3, 4)
HOURS_STEP = 0.25

KIND_LABELS = {
    KIND_MAIN: "Основное",
    KIND_TEMPORARY: "Временное",
    KIND_MONTHLY: "Месячное",
}


class InvalidScheduleVariant(ValueError):
    """Unknown schedule_kind or week_index."""


def normalize_variant(
    kind: str | None = None, week: int | None = None
) -> tuple[str, int]:
    value = (kind or KIND_MAIN).strip().lower()
    if value not in KINDS:
        raise InvalidScheduleVariant(
            f"schedule_kind must be one of {', '.join(KINDS)}"
        )
    if value == KIND_MONTHLY:
        index = 1 if week is None else int(week)
        if index not in MONTHLY_WEEKS:
            raise InvalidScheduleVariant("week_index for monthly must be 1..4")
        return KIND_MONTHLY, index
    return value, 0


def snap_hours(hours: float | int | None) -> float:
    if hours is None:
        return 0.0
    return round(float(hours) * 4) / 4


def is_monthly_only_hours(hours: float | int | None) -> bool:
    value = snap_hours(hours)
    return 0 < value < 1


def format_hours_label(hours: float | int | None) -> str:
    value = snap_hours(hours)
    if value == int(value):
        return str(int(value))
    return f"{value:g}"


def monthly_quota_lessons(hours: float | int | None) -> int:
    """0.25 ч/нед → 1 урок в месяц, 0.5 → 2."""
    value = snap_hours(hours)
    if value <= 0:
        return 0
    return max(1, int(round(value / HOURS_STEP)))
