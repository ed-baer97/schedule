"""Parse a deputy-head phrase into slider updates and optional local-repair intent."""
from __future__ import annotations

from dataclasses import dataclass, field
import re

from app.domain.preferences import WEIGHT_MAX, WEIGHT_MIN, clamp_weight

_PREF_KEYS = (
    "pref_teacher_gaps",
    "pref_hard_subjects_early",
    "pref_adjacent_pairs",
    "pref_classroom_stability",
)

_ORDINALS = (
    ("перв", 1),
    ("втор", 2),
    ("трет", 3),
    ("четверт", 4),
    ("пят", 5),
    ("шест", 6),
    ("седьм", 7),
    ("восьм", 8),
)

_LATE_RE = re.compile(
    r"(?P<subj>[\wЁёА-Яа-я«»\"-]+)\s+"
    r"(?:не\s+)?(?:после|позже)\s+"
    r"(?:(?P<ord>перв\w*|втор\w*|трет\w*|четверт\w*|пят\w*|шест\w*|седьм\w*|восьм\w*)"
    r"|(?P<num>\d+))",
    re.IGNORECASE,
)

_STOP_SUBJ = frozenset(
    {
        "урок",
        "урока",
        "уроки",
        "предмет",
        "предметы",
        "не",
        "после",
        "позже",
        "можно",
        "нужно",
        "надо",
        "пожалуйста",
    }
)


def _fold(text: str) -> str:
    return " ".join(str(text).split()).casefold().replace("ё", "е")


def _intensity(folded: str) -> int:
    if any(w in folded for w in ("не важно", "можно размазать", "выкл", "без предпочт")):
        return WEIGHT_MIN
    if any(
        w in folded
        for w in (
            "только",
            "обязательн",
            "запрет",
            "не после",
            "не позже",
            "максимум",
            "без окон",
        )
    ):
        return WEIGHT_MAX
    return 8


def _ordinal_lesson(token: str) -> int | None:
    t = _fold(token)
    for stem, n in _ORDINALS:
        if t.startswith(stem):
            return n
    return None


def subject_match_stem(raw: str) -> str | None:
    """Short prefix that matches inflected names (физику → физик in Физика)."""
    s = _fold(raw).strip("«»\"'.,;:")
    if len(s) < 4 or s in _STOP_SUBJ:
        return None
    return s[:5]


def _subject_stem(raw: str) -> str | None:
    return subject_match_stem(raw)


@dataclass(frozen=True)
class AssistIntent:
    preference_updates: dict[str, int] = field(default_factory=dict)
    late_subject: str | None = None
    max_lesson: int | None = None
    interpretation: str = ""

    def is_empty(self) -> bool:
        return not self.preference_updates and not (self.late_subject and self.max_lesson)


def parse_assist_intent(message: str) -> AssistIntent:
    """Map Russian scheduler jargon onto existing sliders and a late-subject cap."""
    folded = _fold(message)
    if not folded:
        return AssistIntent(interpretation="Пустой запрос.")

    updates: dict[str, int] = {}
    intensity = _intensity(folded)

    if any(w in folded for w in ("окон", "окна", "окно", "дыр у учител")):
        updates["pref_teacher_gaps"] = intensity
        if "без окон" in folded:
            updates["pref_teacher_gaps"] = WEIGHT_MAX

    if any(w in folded for w in ("сдвоен", "двойк", "пар уроков", "уроки рядом")):
        updates["pref_adjacent_pairs"] = intensity
        if any(w in folded for w in ("только двой", "только пар")):
            updates["pref_adjacent_pairs"] = WEIGHT_MAX

    if any(
        w in folded
        for w in ("сложн", "раньше", "ранние урок", "не после", "не позже")
    ):
        updates["pref_hard_subjects_early"] = intensity

    if any(w in folded for w in ("стабильн", "кабинет", "баланс дней")):
        updates["pref_classroom_stability"] = intensity

    late_subject = None
    max_lesson = None
    m = _LATE_RE.search(message)
    if m:
        late_subject = _subject_stem(m.group("subj") or "")
        if m.group("num"):
            max_lesson = int(m.group("num"))
        elif m.group("ord"):
            max_lesson = _ordinal_lesson(m.group("ord"))
        if max_lesson is not None:
            max_lesson = max(1, min(8, max_lesson))
        if late_subject and max_lesson:
            updates["pref_hard_subjects_early"] = WEIGHT_MAX

    clamped = {
        k: clamp_weight(v)
        for k, v in updates.items()
        if k in _PREF_KEYS
    }

    bits: list[str] = []
    if clamped.get("pref_teacher_gaps") is not None:
        bits.append(f"окна учителей → {clamped['pref_teacher_gaps']}")
    if clamped.get("pref_adjacent_pairs") is not None:
        bits.append(f"сдвоенные → {clamped['pref_adjacent_pairs']}")
    if clamped.get("pref_hard_subjects_early") is not None:
        bits.append(f"сложные раньше → {clamped['pref_hard_subjects_early']}")
    if clamped.get("pref_classroom_stability") is not None:
        bits.append(f"кабинеты/баланс → {clamped['pref_classroom_stability']}")
    if late_subject and max_lesson:
        bits.append(f"сдвинуть «{late_subject}…» с уроков после {max_lesson}")
    interpretation = "; ".join(bits) if bits else "Не распознал правило. Напишите про окна, сдвоенные, ранние уроки или «физику не после пятого»."

    return AssistIntent(
        preference_updates=clamped,
        late_subject=late_subject,
        max_lesson=max_lesson,
        interpretation=interpretation,
    )


def merge_assist_intents(base: AssistIntent, overlay: AssistIntent) -> AssistIntent:
    """Overlay (e.g. LLM) wins on set fields; empty overlay keeps base."""
    updates = dict(base.preference_updates)
    for k, v in overlay.preference_updates.items():
        if k in _PREF_KEYS:
            updates[k] = clamp_weight(v)
    late = overlay.late_subject or base.late_subject
    mx = overlay.max_lesson if overlay.max_lesson is not None else base.max_lesson
    text = overlay.interpretation.strip() or base.interpretation
    return AssistIntent(
        preference_updates=updates,
        late_subject=late,
        max_lesson=mx,
        interpretation=text,
    )
