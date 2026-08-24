"""Assignment service dataclasses."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.models import Subject
from app.services.dto import SchoolClassBriefData, SubjectBriefData


@dataclass
class SubjectAssignClassData:
    id: int
    name: str
    grade: int
    hours_per_week: int
    teacher_ids: list[int]
    is_split: bool


@dataclass
class SubjectAssignTeacherData:
    id: int
    full_name: str


@dataclass
class SubjectOutData:
    id: int
    name: str
    color: str | None
    display_color: str
    requires_fixed_classroom: bool
    default_classroom_id: int | None
    default_classroom: dict | None


@dataclass
class SubjectAssignmentsViewData:
    subject: SubjectOutData
    school_level: str
    classes: list[SubjectAssignClassData]
    attached_teachers: list[SubjectAssignTeacherData]
    all_teachers: list[SubjectAssignTeacherData]


@dataclass
class SubjectAssignmentsSaveResultData:
    ok: bool
    errors: list[str] = field(default_factory=list)


@dataclass
class WorkloadViewData:
    school_level: str
    classes: list[SchoolClassBriefData]
    subjects: list[SubjectBriefData]
    cells: list[tuple[int, int, int]]  # class_id, subject_id, hours


def _subject_out(subject: Subject) -> SubjectOutData:
    dc = subject.default_classroom
    return SubjectOutData(
        id=subject.id,
        name=subject.name,
        color=subject.color,
        display_color=subject.display_color,
        requires_fixed_classroom=bool(subject.requires_fixed_classroom),
        default_classroom_id=subject.default_classroom_id,
        default_classroom=(
            {
                "id": dc.id,
                "number": dc.number,
                "name": dc.name,
                "display_name": dc.display_name,
            }
            if dc
            else None
        ),
    )
