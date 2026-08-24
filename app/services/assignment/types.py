"""Assignment service dataclasses."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.services.dto import (
    SchoolClassBriefData,
    SubjectBriefData,
    SubjectData,
    TeacherBriefData,
)


@dataclass
class SubjectAssignClassData:
    id: int
    name: str
    grade: int
    hours_per_week: int
    teacher_ids: list[int]
    is_split: bool


@dataclass
class SubjectAssignmentsViewData:
    subject: SubjectData
    school_level: str
    classes: list[SubjectAssignClassData]
    attached_teachers: list[TeacherBriefData]
    all_teachers: list[TeacherBriefData]


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
