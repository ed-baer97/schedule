"""Person / name normalization helpers."""


def normalize_person_name(value: str) -> str:
    """Collapse whitespace and casefold for name comparison."""
    return " ".join(str(value).split()).casefold()
