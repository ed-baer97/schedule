"""Subject cycle groups (no DB)."""
from app.domain.subject_group import (
    GROUP_HUMANITIES,
    GROUP_LANGUAGES,
    GROUP_NATURAL_MATH,
    GROUP_PRACTICAL,
    infer_subject_group_from_name,
    normalize_subject_group,
)


def test_legacy_difficulty_maps() -> None:
    assert normalize_subject_group("easy") == GROUP_PRACTICAL
    assert normalize_subject_group("hard") == GROUP_NATURAL_MATH
    assert normalize_subject_group("medium") == GROUP_HUMANITIES
    assert normalize_subject_group("languages") == GROUP_LANGUAGES
    assert normalize_subject_group(None) == GROUP_HUMANITIES


def test_infer_from_typical_names() -> None:
    assert infer_subject_group_from_name("Математика") == GROUP_NATURAL_MATH
    assert infer_subject_group_from_name("Физика") == GROUP_NATURAL_MATH
    assert infer_subject_group_from_name("Английский язык") == GROUP_LANGUAGES
    assert infer_subject_group_from_name("Казахский язык") == GROUP_LANGUAGES
    assert infer_subject_group_from_name("История Казахстана") == GROUP_HUMANITIES
    assert infer_subject_group_from_name("Физкультура") == GROUP_PRACTICAL
    assert infer_subject_group_from_name("Физическая культура") == GROUP_PRACTICAL
    assert infer_subject_group_from_name("НВП") == GROUP_PRACTICAL
    assert infer_subject_group_from_name("Технология") == GROUP_PRACTICAL
    assert infer_subject_group_from_name("Непонятный курс") is None
