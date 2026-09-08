"""Subject cycle groups (replaces easy/medium/hard)."""
from __future__ import annotations

GROUP_NATURAL_MATH = "natural_math"
GROUP_HUMANITIES = "humanities"
GROUP_LANGUAGES = "languages"
GROUP_PRACTICAL = "practical"

SUBJECT_GROUPS = (
    GROUP_NATURAL_MATH,
    GROUP_HUMANITIES,
    GROUP_LANGUAGES,
    GROUP_PRACTICAL,
)

DEFAULT_SUBJECT_GROUP = GROUP_HUMANITIES

GROUP_LABELS_RU = {
    GROUP_NATURAL_MATH: "Естественно-математический",
    GROUP_HUMANITIES: "Гуманитарный",
    GROUP_LANGUAGES: "Языки",
    GROUP_PRACTICAL: "Практические",
}

_LEGACY_DIFFICULTY = {
    "easy": GROUP_PRACTICAL,
    "hard": GROUP_NATURAL_MATH,
    "medium": GROUP_HUMANITIES,
}

_LANGUAGE_STEMS = (
    "англий",
    "русск",
    "казахск",
    "немец",
    "француз",
    "китайск",
    "уйгур",
    "турецк",
    "литерат",
    "иностран",
)
_PRACTICAL_STEMS = (
    "физкультур",
    "физ-ра",
    "физра",
    "физическ культур",
    "труд",
    "технолог",
    "нвп",
    "обж",
    "военн",
    "черчен",
    "график",
)
_STEM_STEMS = (
    "математ",
    "алгебр",
    "геометр",
    "физик",
    "хими",
    "биологи",
    "информат",
    "естество",
    "природов",
)
_HUMANITIES_STEMS = (
    "истори",
    "общество",
    "право",
    "географ",
    "экономи",
    "этик",
    "религи",
    "краевед",
)


def _fold_name(name: str) -> str:
    return " ".join(str(name).split()).casefold().replace("ё", "е")


def normalize_subject_group(value: str | None) -> str:
    raw = (value or "").strip().lower()
    if raw in SUBJECT_GROUPS:
        return raw
    return _LEGACY_DIFFICULTY.get(raw, DEFAULT_SUBJECT_GROUP)


def infer_subject_group_from_name(name: str) -> str | None:
    """Guess a cycle from a typical school subject title, or None if unclear."""
    n = _fold_name(name)
    if not n:
        return None
    if any(s in n for s in _HUMANITIES_STEMS):
        return GROUP_HUMANITIES
    if any(s in n for s in _LANGUAGE_STEMS):
        return GROUP_LANGUAGES
    if any(s in n for s in _PRACTICAL_STEMS):
        return GROUP_PRACTICAL
    if "культур" in n and any(
        s in n for s in ("физическ", "физкультур", "физра", "физ-ра")
    ):
        return GROUP_PRACTICAL
    if any(s in n for s in _STEM_STEMS):
        return GROUP_NATURAL_MATH
    return None
