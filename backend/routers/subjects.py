"""Subjects CRUD API."""
from dataclasses import asdict

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.models import School
from app.services.assignment_service import AssignmentService
from app.services.subject_service import SubjectService
from backend.deps import get_current_school, get_db
from backend.schemas.subjects import (
    SubjectAssignClassRow,
    SubjectAssignmentsSave,
    SubjectAssignmentsSaveResult,
    SubjectAssignmentsView,
    SubjectAssignTeacherRow,
    SubjectColorOut,
    SubjectColorUpdate,
    SubjectCreate,
    SubjectOut,
    SubjectUpdate,
)

router = APIRouter()


@router.get("/", response_model=list[SubjectOut])
def list_subjects(
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
    school_level: str | None = Query(None, pattern="^(elementary|secondary)$"),
) -> list[SubjectOut]:
    return [
        SubjectOut.model_validate(asdict(s))
        for s in SubjectService(db, school.id).list(school_level)
    ]


@router.get("/meta/color-palette", response_model=list[str])
def color_palette() -> list[str]:
    return SubjectService.color_palette()


@router.get("/{subject_id}", response_model=SubjectOut)
def get_subject(
    subject_id: int,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> SubjectOut:
    return SubjectOut.model_validate(
        asdict(SubjectService(db, school.id).get(subject_id))
    )


@router.post("/", response_model=SubjectOut)
def create_subject(
    body: SubjectCreate,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> SubjectOut:
    s = SubjectService(db, school.id).create(
        name=body.name,
        color=body.color,
        requires_fixed_classroom=body.requires_fixed_classroom,
        default_classroom_id=body.default_classroom_id,
    )
    return SubjectOut.model_validate(asdict(s))


@router.put("/{subject_id}", response_model=SubjectOut)
def update_subject(
    subject_id: int,
    body: SubjectUpdate,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> SubjectOut:
    data = body.model_dump(exclude_unset=True)
    s = SubjectService(db, school.id).update(
        subject_id,
        name=data.get("name"),
        color=data.get("color"),
        requires_fixed_classroom=data.get("requires_fixed_classroom"),
        default_classroom_id=data.get("default_classroom_id"),
        fields_set=frozenset(data.keys()),
    )
    return SubjectOut.model_validate(asdict(s))


@router.patch("/{subject_id}/color", response_model=SubjectColorOut)
def set_subject_color(
    subject_id: int,
    body: SubjectColorUpdate,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> SubjectColorOut:
    """Quick color change from the subjects list."""
    result = SubjectService(db, school.id).set_color(subject_id, body.color)
    return SubjectColorOut(id=result.id, display_color=result.display_color)


@router.delete("/{subject_id}", status_code=204)
def delete_subject(
    subject_id: int,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> None:
    SubjectService(db, school.id).delete(subject_id)


@router.get("/{subject_id}/assignments", response_model=SubjectAssignmentsView)
def get_subject_assignments(
    subject_id: int,
    school_level: str = Query("elementary", pattern="^(elementary|secondary)$"),
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> SubjectAssignmentsView:
    data = AssignmentService(db, school.id).get_subject_assignments(
        subject_id, school_level
    )
    return SubjectAssignmentsView(
        subject=SubjectOut.model_validate(asdict(data.subject)),
        school_level=data.school_level,
        classes=[
            SubjectAssignClassRow(
                id=c.id,
                name=c.name,
                grade=c.grade,
                hours_per_week=c.hours_per_week,
                teacher_ids=c.teacher_ids,
                is_split=c.is_split,
            )
            for c in data.classes
        ],
        attached_teachers=[
            SubjectAssignTeacherRow(id=t.id, full_name=t.full_name)
            for t in data.attached_teachers
        ],
        all_teachers=[
            SubjectAssignTeacherRow(id=t.id, full_name=t.full_name)
            for t in data.all_teachers
        ],
    )


@router.post(
    "/{subject_id}/assignments", response_model=SubjectAssignmentsSaveResult
)
def save_subject_assignments(
    subject_id: int,
    body: SubjectAssignmentsSave,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> SubjectAssignmentsSaveResult:
    result = AssignmentService(db, school.id).save_subject_assignments(
        subject_id,
        school_level=body.school_level,
        teacher_ids=body.teacher_ids,
        selections=body.selections,
    )
    return SubjectAssignmentsSaveResult(ok=result.ok, errors=result.errors)
