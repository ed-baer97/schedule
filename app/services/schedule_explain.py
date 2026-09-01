"""Explain a grid slot from validator facts; Qwen only phrases the text."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from sqlalchemy.orm import Session, joinedload

from app.domain.days import DAY_NAMES
from app.domain.shift_grid import lesson_end_exclusive
from app.models import SchoolClass, TeachingAssignment
from app.services.assignment_hours import placed_count, remaining_for
from app.services.classroom_resolver import pick_classroom_for
from app.services.errors import NotFoundError
from app.services.qwen_client import phrase_for_scheduler
from app.services.tenancy import require_owned
from app.services.validators import ScheduleValidator

_PHRASE_SYSTEM = (
    "Ты помощник завуча. Ниже JSON с проверенными фактами валидатора расписания. "
    "Перескажи их коротко по-русски (2–6 предложений). "
    "Не добавляй факты, которых нет в JSON. Не предлагай нарушать конфликты. "
    "Если allowed=false, сначала назови причины. Затем перечисли alternatives, если они есть."
)


@dataclass
class SlotOption:
    day_of_week: int
    lesson_number: int
    day_name: str
    label: str


@dataclass
class ExplainResult:
    allowed: bool
    blockers: list[str]
    alternatives: list[SlotOption]
    text: str
    llm_used: bool
    facts: dict = field(default_factory=dict)


def _day_name(day: int) -> str:
    if 1 <= day <= len(DAY_NAMES):
        return DAY_NAMES[day - 1]
    return f"день {day}"


def _slot_label(day: int, lesson: int) -> str:
    lesson_txt = "классный час" if lesson == 0 else f"урок {lesson}"
    return f"{_day_name(day)}, {lesson_txt}"


def _fallback_text(facts: dict) -> str:
    subj = facts["assignment"]["subject"]
    teacher = facts["assignment"]["teacher"] or "без учителя"
    klass = facts["assignment"]["class_name"]
    slot = facts["slot"]["label"]
    lines: list[str] = []
    if facts["allowed"]:
        lines.append(f"Сюда можно поставить «{subj}» ({teacher}) для {klass}: {slot}.")
    else:
        lines.append(f"Сюда нельзя поставить «{subj}» ({teacher}) для {klass}: {slot}.")
        for b in facts["blockers"]:
            lines.append(f"— {b}")
    alts = facts.get("alternatives") or []
    if alts:
        labels = "; ".join(a["label"] for a in alts[:8])
        lines.append(f"Свободные слоты: {labels}.")
    elif not facts["allowed"]:
        lines.append("Других свободных слотов в сетке смены сейчас нет.")
    return "\n".join(lines)


class ScheduleExplainService:
    def __init__(self, db: Session, school_id: int):
        self.db = db
        self.school_id = school_id
        self.validator = ScheduleValidator(db, school_id)

    def explain_slot(
        self,
        *,
        assignment_id: int,
        day_of_week: int,
        lesson_number: int,
        classroom_id: int | None = None,
        cell_id: int | None = None,
    ) -> ExplainResult:
        require_owned(self.db, TeachingAssignment, assignment_id, self.school_id)
        assignment = (
            self.db.query(TeachingAssignment)
            .options(
                joinedload(TeachingAssignment.subject),
                joinedload(TeachingAssignment.teacher),
                joinedload(TeachingAssignment.school_class).joinedload(SchoolClass.shift),
            )
            .filter(
                TeachingAssignment.id == assignment_id,
                TeachingAssignment.school_id == self.school_id,
            )
            .one_or_none()
        )
        if assignment is None:
            raise NotFoundError("Назначение не найдено")

        school_class = assignment.school_class
        school_level = school_class.school_level if school_class else "elementary"
        if classroom_id is None:
            classroom_id = pick_classroom_for(
                self.db,
                self.school_id,
                assignment,
                school_level,
                day=day_of_week,
                lesson=lesson_number,
                exclude_cell_id=cell_id,
            )

        blockers = self.validator.validate_cell(
            assignment,
            day_of_week,
            lesson_number,
            classroom_id=classroom_id,
            exclude_cell_id=cell_id,
        )
        alternatives = self._alternatives(
            assignment,
            classroom_id=classroom_id,
            exclude_cell_id=cell_id,
            skip=(day_of_week, lesson_number),
        )
        remaining = remaining_for(
            assignment, placed=placed_count(self.db, assignment.id)
        )
        facts = {
            "slot": {
                "day_of_week": day_of_week,
                "lesson_number": lesson_number,
                "label": _slot_label(day_of_week, lesson_number),
            },
            "assignment": {
                "id": assignment.id,
                "subject": assignment.subject.display_name if assignment.subject else "?",
                "teacher": assignment.teacher.display_name if assignment.teacher else None,
                "class_name": school_class.name if school_class else "?",
                "group_number": assignment.group_number,
                "remaining_hours": remaining,
            },
            "allowed": not blockers,
            "blockers": list(blockers),
            "alternatives": [
                {
                    "day_of_week": a.day_of_week,
                    "lesson_number": a.lesson_number,
                    "label": a.label,
                }
                for a in alternatives
            ],
        }
        phrased = phrase_for_scheduler(
            json.dumps(facts, ensure_ascii=False),
            system=_PHRASE_SYSTEM,
        )
        return ExplainResult(
            allowed=not blockers,
            blockers=list(blockers),
            alternatives=alternatives,
            text=phrased or _fallback_text(facts),
            llm_used=bool(phrased),
            facts=facts,
        )

    def _alternatives(
        self,
        assignment: TeachingAssignment,
        *,
        classroom_id: int | None,
        exclude_cell_id: int | None,
        skip: tuple[int, int],
        limit: int = 8,
    ) -> list[SlotOption]:
        school_class = assignment.school_class
        shift = school_class.shift if school_class and school_class.shift_id else None
        working_days = shift.working_days if shift else 5
        start = shift.start_lesson if shift else 1
        found: list[SlotOption] = []
        for day in range(1, working_days + 1):
            end = lesson_end_exclusive(shift, day) if shift else start + 7
            for lesson in range(start, end):
                if (day, lesson) == skip:
                    continue
                errors = self.validator.validate_cell(
                    assignment,
                    day,
                    lesson,
                    classroom_id=classroom_id,
                    exclude_cell_id=exclude_cell_id,
                )
                if errors:
                    continue
                found.append(
                    SlotOption(
                        day_of_week=day,
                        lesson_number=lesson,
                        day_name=_day_name(day),
                        label=_slot_label(day, lesson),
                    )
                )
                if len(found) >= limit:
                    return found
        return found
