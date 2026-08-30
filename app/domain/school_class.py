"""School class name helpers."""
from dataclasses import dataclass
from typing import Iterable, TypeVar

SPLIT_WHOLE_SHIFT = "shift"
SPLIT_GRADE_BANDS = "grade_bands"

_T = TypeVar("_T")


def grade_from_name(name: str) -> int:
    grade_str = "".join(ch for ch in name if ch.isdigit())
    return int(grade_str) if grade_str else 1


def level_from_grade(grade: int) -> str:
    """Map numeric grade to school_level."""
    return "elementary" if int(grade) <= 4 else "secondary"


@dataclass(frozen=True)
class GradeBand:
    grade_min: int
    grade_max: int
    label: str

    def contains(self, grade: int) -> bool:
        return self.grade_min <= int(grade) <= self.grade_max


def grade_bands_for_level(school_level: str) -> tuple[GradeBand, ...]:
    """CP-SAT chunks inside one shift. Secondary 7–9 also absorbs 10–11."""
    if school_level == "elementary":
        return (
            GradeBand(1, 2, "1–2 классы"),
            GradeBand(3, 4, "3–4 классы"),
        )
    return (
        GradeBand(5, 6, "5–6 классы"),
        GradeBand(7, 11, "7–9 классы"),
    )


def partition_classes_by_grade_bands(
    classes: Iterable[_T], school_level: str
) -> list[tuple[GradeBand, list[_T]]]:
    """Group classes into non-empty bands; out-of-range grades join the last band."""
    bands = grade_bands_for_level(school_level)
    buckets: list[list[_T]] = [[] for _ in bands]
    overflow: list[_T] = []
    for cls in classes:
        grade = int(getattr(cls, "grade", 0) or 0)
        placed = False
        for i, band in enumerate(bands):
            if band.contains(grade):
                buckets[i].append(cls)
                placed = True
                break
        if not placed:
            overflow.append(cls)
    if overflow and buckets:
        buckets[-1].extend(overflow)
    return [(band, items) for band, items in zip(bands, buckets) if items]
