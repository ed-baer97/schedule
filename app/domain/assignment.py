"""Pure helpers for teaching-assignment hours (no Session)."""


def remaining_hours(hours_per_week: int, placed: int) -> int:
    return max(0, int(hours_per_week) - int(placed))


def hours_exhausted(hours_per_week: int, placed: int) -> bool:
    return remaining_hours(hours_per_week, placed) <= 0
