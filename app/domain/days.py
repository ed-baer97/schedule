"""Weekday labels and time formatting."""
from __future__ import annotations

from typing import Any

DAY_NAMES: list[str] = [
    "Понедельник",
    "Вторник",
    "Среда",
    "Четверг",
    "Пятница",
    "Суббота",
]

SHORT_DAY_NAMES: list[str] = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб"]


def fmt_time(t: Any) -> str | None:
    if t is None:
        return None
    return t.strftime("%H:%M") if hasattr(t, "strftime") else str(t)


def time_range_label(start: Any, end: Any) -> str | None:
    a, b = fmt_time(start), fmt_time(end)
    if a and b:
        return f"{a}–{b}"
    return None
