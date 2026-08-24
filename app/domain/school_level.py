"""School level labels (UI display strings)."""


def level_label(level: str) -> str:
    return "Начальная школа" if level == "elementary" else "Основная школа"
