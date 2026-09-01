"""Natural-language assist: map a phrase to sliders and validated local moves.

Qwen may refine the *intent*. It never chooses cell ids or writes the grid.
Moves go through ScheduleValidator then ScheduleService.move_cell.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session, joinedload

from app.domain.assist_intent import (
    AssistIntent,
    merge_assist_intents,
    parse_assist_intent,
    subject_match_stem,
)
from app.domain.days import DAY_NAMES
from app.domain.preferences import clamp_weight
from app.domain.shift_grid import lesson_end_exclusive
from app.models import ScheduleCell, SchoolClass, TeachingAssignment
from app.services.classroom_resolver import load_settings
from app.services.errors import ValidationConflict
from app.services.qwen_client import complete_json, qwen_configured
from app.services.schedule_service import ScheduleService
from app.services.validators import ScheduleValidator

_MAX_MOVES = 8

_INTENT_SYSTEM = (
    "Ты помощник завуча. По фразе верни JSON без markdown со полями: "
    "pref_teacher_gaps, pref_hard_subjects_early, pref_adjacent_pairs, "
    "pref_classroom_stability (число 0–10 или null), "
    "late_subject (корень названия предмета или null), "
    "max_lesson (1–8 или null — уроки строго позже этого номера сдвинуть раньше), "
    "interpretation (кратко по-русски). "
    "Не выдумывай cell_id. Не предлагай нарушать конфликты. "
    "Неизвестное поле — null."
)


@dataclass
class ProposedMove:
    cell_id: int
    subject: str
    class_name: str
    from_day: int
    from_lesson: int
    to_day: int
    to_lesson: int
    allowed: bool
    blockers: list[str] = field(default_factory=list)
    applied: bool = False
    label: str = ""


@dataclass
class AssistResult:
    interpretation: str
    llm_used: bool
    preference_updates: dict[str, int]
    preferences_applied: bool
    moves: list[ProposedMove]
    applied_moves: int
    rejected: list[ProposedMove]


def _day_name(day: int) -> str:
    if 1 <= day <= len(DAY_NAMES):
        return DAY_NAMES[day - 1]
    return f"день {day}"


def _intent_from_llm_dict(data: dict) -> AssistIntent:
    updates = {}
    for key in (
        "pref_teacher_gaps",
        "pref_hard_subjects_early",
        "pref_adjacent_pairs",
        "pref_classroom_stability",
    ):
        raw = data.get(key)
        if raw is None or raw == "":
            continue
        try:
            updates[key] = clamp_weight(int(raw))
        except (TypeError, ValueError):
            continue
    late = data.get("late_subject")
    late_s = subject_match_stem(str(late)) if late else None
    mx = data.get("max_lesson")
    max_lesson = None
    if mx is not None and mx != "":
        try:
            max_lesson = max(1, min(8, int(mx)))
        except (TypeError, ValueError):
            max_lesson = None
    text = str(data.get("interpretation") or "").strip()
    return AssistIntent(
        preference_updates=updates,
        late_subject=late_s,
        max_lesson=max_lesson,
        interpretation=text,
    )


class ScheduleAssistService:
    def __init__(self, db: Session, school_id: int):
        self.db = db
        self.school_id = school_id
        self.validator = ScheduleValidator(db, school_id)
        self._schedule = ScheduleService(db, school_id)

    def run(
        self,
        *,
        message: str,
        school_level: str,
        shift_id: int | None = None,
        apply: bool = False,
    ) -> AssistResult:
        intent = parse_assist_intent(message)
        llm_used = False
        if qwen_configured():
            overlay_raw = complete_json(message, system=_INTENT_SYSTEM)
            if overlay_raw:
                intent = merge_assist_intents(intent, _intent_from_llm_dict(overlay_raw))
                llm_used = True

        moves: list[ProposedMove] = []
        if intent.late_subject and intent.max_lesson:
            moves = self._propose_early_moves(
                subject_stem=intent.late_subject,
                max_lesson=intent.max_lesson,
                school_level=school_level,
                shift_id=shift_id,
            )

        prefs_applied = False
        if apply and intent.preference_updates:
            self._apply_preferences(school_level, intent.preference_updates)
            prefs_applied = True

        applied_n = 0
        rejected: list[ProposedMove] = []
        kept: list[ProposedMove] = []
        if apply:
            for mv in moves:
                if not mv.allowed:
                    rejected.append(mv)
                    continue
                try:
                    self._schedule.move_cell(
                        mv.cell_id,
                        day_of_week=mv.to_day,
                        lesson_number=mv.to_lesson,
                    )
                except ValidationConflict as exc:
                    mv.allowed = False
                    mv.blockers = list(exc.errors)
                    rejected.append(mv)
                    continue
                mv.applied = True
                applied_n += 1
                kept.append(mv)
        else:
            for mv in moves:
                if mv.allowed:
                    kept.append(mv)
                else:
                    rejected.append(mv)

        return AssistResult(
            interpretation=intent.interpretation,
            llm_used=llm_used,
            preference_updates=dict(intent.preference_updates),
            preferences_applied=prefs_applied,
            moves=kept,
            applied_moves=applied_n,
            rejected=rejected,
        )

    def _apply_preferences(self, school_level: str, updates: dict[str, int]) -> None:
        row = load_settings(self.db, self.school_id, school_level)
        max_per = row.max_lessons_per_subject_per_day if row else 2
        mode = row.classroom_mode if row else "class_room"
        leave = row.elementary_group_subjects_leave if row else True
        self._schedule.update_settings(
            school_level,
            max_lessons_per_subject_per_day=max_per,
            classroom_mode=mode,
            elementary_group_subjects_leave=leave,
            pref_teacher_gaps=updates.get("pref_teacher_gaps"),
            pref_hard_subjects_early=updates.get("pref_hard_subjects_early"),
            pref_adjacent_pairs=updates.get("pref_adjacent_pairs"),
            pref_classroom_stability=updates.get("pref_classroom_stability"),
        )

    def _propose_early_moves(
        self,
        *,
        subject_stem: str,
        max_lesson: int,
        school_level: str,
        shift_id: int | None,
    ) -> list[ProposedMove]:
        q = (
            self.db.query(ScheduleCell)
            .join(TeachingAssignment, ScheduleCell.assignment_id == TeachingAssignment.id)
            .join(SchoolClass, ScheduleCell.class_id == SchoolClass.id)
            .options(
                joinedload(ScheduleCell.assignment).joinedload(TeachingAssignment.subject),
                joinedload(ScheduleCell.school_class).joinedload(SchoolClass.shift),
            )
            .filter(
                ScheduleCell.school_id == self.school_id,
                SchoolClass.school_id == self.school_id,
                SchoolClass.school_level == school_level,
                ScheduleCell.lesson_number > max_lesson,
            )
        )
        if shift_id is not None:
            q = q.filter(SchoolClass.shift_id == int(shift_id))
        cells = q.order_by(
            ScheduleCell.lesson_number.desc(),
            ScheduleCell.day_of_week,
            ScheduleCell.id,
        ).all()

        stem = subject_stem.casefold().replace("ё", "е")
        out: list[ProposedMove] = []
        for cell in cells:
            subj = ""
            if cell.assignment and cell.assignment.subject:
                subj = (cell.assignment.subject.display_name or cell.assignment.subject.name or "")
            if stem not in subj.casefold().replace("ё", "е"):
                continue
            target = self._first_early_slot(cell, max_lesson)
            class_name = cell.school_class.name if cell.school_class else "?"
            if target is None:
                out.append(
                    ProposedMove(
                        cell_id=cell.id,
                        subject=subj or "?",
                        class_name=class_name,
                        from_day=cell.day_of_week,
                        from_lesson=cell.lesson_number,
                        to_day=cell.day_of_week,
                        to_lesson=cell.lesson_number,
                        allowed=False,
                        blockers=["Нет свободного слота не позже указанного урока"],
                        label=(
                            f"{subj} {class_name}: {_day_name(cell.day_of_week)} "
                            f"урок {cell.lesson_number} — некуда сдвинуть"
                        ),
                    )
                )
            else:
                to_day, to_lesson, blockers = target
                allowed = not blockers
                out.append(
                    ProposedMove(
                        cell_id=cell.id,
                        subject=subj or "?",
                        class_name=class_name,
                        from_day=cell.day_of_week,
                        from_lesson=cell.lesson_number,
                        to_day=to_day,
                        to_lesson=to_lesson,
                        allowed=allowed,
                        blockers=list(blockers),
                        label=(
                            f"{subj} {class_name}: {_day_name(cell.day_of_week)} "
                            f"урок {cell.lesson_number} → {_day_name(to_day)} урок {to_lesson}"
                        ),
                    )
                )
            if len(out) >= _MAX_MOVES:
                break
        return out

    def _first_early_slot(
        self, cell: ScheduleCell, max_lesson: int
    ) -> tuple[int, int, list[str]] | None:
        assignment = cell.assignment
        school_class = cell.school_class
        shift = school_class.shift if school_class and school_class.shift_id else None
        working_days = shift.working_days if shift else 5
        start = shift.start_lesson if shift else 1
        end = lesson_end_exclusive(shift) if shift else start + 7
        cap = min(max_lesson, end - 1)
        if cap < start:
            return None

        day_order = [cell.day_of_week] + [
            d for d in range(1, working_days + 1) if d != cell.day_of_week
        ]
        for day in day_order:
            day_end = min(cap, (lesson_end_exclusive(shift, day) if shift else end) - 1)
            for lesson in range(start, day_end + 1):
                if day == cell.day_of_week and lesson == cell.lesson_number:
                    continue
                errors = self.validator.validate_cell(
                    assignment,
                    day,
                    lesson,
                    classroom_id=cell.classroom_id,
                    exclude_cell_id=cell.id,
                )
                if not errors:
                    return day, lesson, []
        return None
