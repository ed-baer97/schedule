"""Parse deputy-head phrases into slider / late-subject intent (no DB)."""
from app.domain.assist_intent import parse_assist_intent


def test_windows_phrase_sets_teacher_gaps():
    intent = parse_assist_intent("без окон у учителя")
    assert intent.preference_updates["pref_teacher_gaps"] == 10
    assert intent.late_subject is None


def test_pairs_phrase_sets_adjacent_slider():
    intent = parse_assist_intent("только двойки, сдвоенные уроки рядом")
    assert intent.preference_updates["pref_adjacent_pairs"] == 10


def test_physics_not_after_fifth_sets_early_and_late_cap():
    intent = parse_assist_intent("физику не после пятого")
    assert intent.preference_updates["pref_hard_subjects_early"] == 10
    assert intent.late_subject == "физик"
    assert intent.max_lesson == 5


def test_physics_not_after_digit():
    intent = parse_assist_intent("Физика не после 5 урока")
    assert intent.late_subject is not None
    assert intent.late_subject.startswith("физик")
    assert intent.max_lesson == 5


def test_unknown_phrase_is_empty():
    intent = parse_assist_intent("сделай красиво")
    assert intent.is_empty()
