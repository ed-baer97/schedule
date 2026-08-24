"""School class name helpers."""


def grade_from_name(name: str) -> int:
    grade_str = "".join(ch for ch in name if ch.isdigit())
    return int(grade_str) if grade_str else 1


def level_from_grade(grade: int) -> str:
    """Map numeric grade to school_level."""
    return "elementary" if int(grade) <= 4 else "secondary"
