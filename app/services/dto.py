"""Shared service-layer DTOs (no ORM / FastAPI)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ClassroomBriefData:
    id: int
    number: str
    name: str | None = None
    display_name: str = ""


@dataclass
class TeacherBriefData:
    id: int
    full_name: str


@dataclass
class SchoolClassBriefData:
    id: int
    name: str
    school_level: str
    grade: int


@dataclass
class SubjectBriefData:
    id: int
    name: str
    color: str | None = None
    display_color: str = ""


@dataclass
class SchoolClassRowData:
    id: int
    name: str
    grade: int
    school_level: str
    shift_id: int | None = None
    home_classroom_id: int | None = None


@dataclass
class ScheduleSettingsData:
    school_level: str
    max_lessons_per_subject_per_day: int
    classroom_mode: str
    elementary_group_subjects_leave: bool
    pref_teacher_gaps: int = 5
    pref_hard_subjects_early: int = 5
    pref_adjacent_pairs: int = 5
    pref_classroom_stability: int = 5


@dataclass
class ClassroomChoiceData:
    id: int
    number: str
    name: str | None
    display_name: str


@dataclass
class ClassroomWarningData:
    type: str
    message: str


@dataclass
class AssignmentData:
    id: int
    subject_id: int
    teacher_id: int | None
    class_id: int
    hours_per_week: int
    group_number: int | None
    preferred_classroom_id: int | None
    subject: SubjectBriefData
    teacher: TeacherBriefData | None
    school_class: SchoolClassBriefData
    preferred_classroom: ClassroomBriefData | None


@dataclass
class TeacherData:
    id: int
    full_name: str
    email: str | None
    phone: str | None
    home_classroom_id: int | None
    home_classroom: ClassroomBriefData | None


@dataclass
class ClassroomData:
    id: int
    number: str
    name: str | None
    capacity: int | None
    classes_capacity: int | None
    floor: int | None
    building: str | None
    display_name: str


@dataclass
class SubjectData:
    id: int
    name: str
    color: str | None
    display_color: str
    requires_fixed_classroom: bool
    default_classroom_id: int | None
    default_classroom: ClassroomBriefData | None


@dataclass
class ShiftBriefNestedData:
    id: int
    name: str
    school_level: str


@dataclass
class SchoolClassData:
    id: int
    name: str
    grade: int
    school_level: str
    school_level_display: str
    shift_id: int | None
    students_count: int | None
    home_classroom_id: int | None
    homeroom_teacher_id: int | None
    shift: ShiftBriefNestedData | None
    home_classroom: ClassroomBriefData | None
    homeroom_teacher: TeacherBriefData | None


def classroom_brief(c) -> ClassroomBriefData:
    return ClassroomBriefData(
        id=c.id,
        number=c.number,
        name=c.name,
        display_name=c.display_name,
    )


def teacher_brief(t) -> TeacherBriefData:
    return TeacherBriefData(id=t.id, full_name=t.full_name)


def school_class_brief(sc) -> SchoolClassBriefData:
    return SchoolClassBriefData(
        id=sc.id,
        name=sc.name,
        school_level=sc.school_level,
        grade=sc.grade,
    )


def subject_brief(s) -> SubjectBriefData:
    return SubjectBriefData(
        id=s.id,
        name=s.name,
        color=s.color,
        display_color=s.display_color,
    )


def school_class_row(sc) -> SchoolClassRowData:
    return SchoolClassRowData(
        id=sc.id,
        name=sc.name,
        grade=sc.grade,
        school_level=sc.school_level,
        shift_id=sc.shift_id,
        home_classroom_id=sc.home_classroom_id,
    )


def settings_data(s) -> ScheduleSettingsData:
    return ScheduleSettingsData(
        school_level=s.school_level,
        max_lessons_per_subject_per_day=s.max_lessons_per_subject_per_day,
        classroom_mode=s.classroom_mode,
        elementary_group_subjects_leave=s.elementary_group_subjects_leave,
        pref_teacher_gaps=int(getattr(s, "pref_teacher_gaps", 5) or 5),
        pref_hard_subjects_early=int(getattr(s, "pref_hard_subjects_early", 5) or 5),
        pref_adjacent_pairs=int(getattr(s, "pref_adjacent_pairs", 5) or 5),
        pref_classroom_stability=int(getattr(s, "pref_classroom_stability", 5) or 5),
    )


def classroom_choice(c) -> ClassroomChoiceData:
    return ClassroomChoiceData(
        id=c.id,
        number=c.number,
        name=c.name,
        display_name=c.display_name,
    )


def assignment_data(a) -> AssignmentData:
    return AssignmentData(
        id=a.id,
        subject_id=a.subject_id,
        teacher_id=a.teacher_id,
        class_id=a.class_id,
        hours_per_week=a.hours_per_week,
        group_number=a.group_number,
        preferred_classroom_id=a.preferred_classroom_id,
        subject=subject_brief(a.subject),
        teacher=teacher_brief(a.teacher) if a.teacher else None,
        school_class=school_class_brief(a.school_class),
        preferred_classroom=(
            classroom_brief(a.preferred_classroom) if a.preferred_classroom else None
        ),
    )


def teacher_data(t) -> TeacherData:
    return TeacherData(
        id=t.id,
        full_name=t.full_name,
        email=t.email,
        phone=t.phone,
        home_classroom_id=t.home_classroom_id,
        home_classroom=(
            classroom_brief(t.home_classroom) if t.home_classroom else None
        ),
    )


def classroom_data(c) -> ClassroomData:
    return ClassroomData(
        id=c.id,
        number=c.number,
        name=c.name,
        capacity=c.capacity,
        classes_capacity=c.classes_capacity,
        floor=c.floor,
        building=c.building,
        display_name=c.display_name,
    )


def subject_data(s) -> SubjectData:
    return SubjectData(
        id=s.id,
        name=s.name,
        color=s.color,
        display_color=s.display_color,
        requires_fixed_classroom=bool(s.requires_fixed_classroom),
        default_classroom_id=s.default_classroom_id,
        default_classroom=(
            classroom_brief(s.default_classroom) if s.default_classroom else None
        ),
    )


def school_class_data(sc) -> SchoolClassData:
    return SchoolClassData(
        id=sc.id,
        name=sc.name,
        grade=sc.grade,
        school_level=sc.school_level,
        school_level_display=sc.school_level_display,
        shift_id=sc.shift_id,
        students_count=sc.students_count,
        home_classroom_id=sc.home_classroom_id,
        homeroom_teacher_id=sc.homeroom_teacher_id,
        shift=(
            ShiftBriefNestedData(
                id=sc.shift.id, name=sc.shift.name, school_level=sc.shift.school_level
            )
            if sc.shift
            else None
        ),
        home_classroom=(
            classroom_brief(sc.home_classroom) if sc.home_classroom else None
        ),
        homeroom_teacher=(
            teacher_brief(sc.homeroom_teacher) if sc.homeroom_teacher else None
        ),
    )
