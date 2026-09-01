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


def split_time_range(label: str | None) -> tuple[str, str] | None:
    """Split ``08:00–08:45`` into start/end; accepts en-dash, em-dash, hyphen."""
    if not label:
        return None
    for sep in ("–", "—", "-"):
        idx = label.find(sep)
        if idx <= 0:
            continue
        start, end = label[:idx].strip(), label[idx + len(sep) :].strip()
        if start and end:
            return start, end
    return None


def hm_to_minutes(value: str) -> int | None:
    parts = value.strip().split(":")
    if len(parts) != 2:
        return None
    try:
        hours, minutes = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if hours > 23 or minutes > 59:
        return None
    return hours * 60 + minutes


def break_between_labels(
    prev_label: str | None, next_label: str | None
) -> tuple[int, str] | None:
    """Gap after one lesson (or class hour) and before the next, in minutes + range."""
    prev_parts = split_time_range(prev_label)
    next_parts = split_time_range(next_label)
    if not prev_parts or not next_parts:
        return None
    start = hm_to_minutes(prev_parts[1])
    end = hm_to_minutes(next_parts[0])
    if start is None or end is None:
        return None
    minutes = end - start
    if minutes <= 0:
        return None
    return minutes, f"{prev_parts[1]}–{next_parts[0]}"
