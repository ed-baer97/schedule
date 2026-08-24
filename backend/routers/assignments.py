"""Teaching assignments CRUD (teacher↔subject↔class link)."""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.models import School
from app.services.assignment_service import AssignmentService
from backend.deps import get_current_school, get_db
from backend.schemas.assignments import (
    AssignmentCreate,
    AssignmentOut,
    AssignmentUpdate,
    AssignTeacherBody,
)

router = APIRouter()


@router.get("/", response_model=list[AssignmentOut])
def list_assignments(
    school_level: str | None = Query(None, pattern="^(elementary|secondary)$"),
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> list[AssignmentOut]:
    rows = AssignmentService(db, school.id).list(school_level)
    return [AssignmentOut.model_validate(asdict(a)) for a in rows]


@router.get("/{assignment_id}", response_model=AssignmentOut)
def get_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> AssignmentOut:
    return AssignmentOut.model_validate(
        asdict(AssignmentService(db, school.id).get(assignment_id))
    )


@router.post("/", response_model=AssignmentOut, status_code=201)
def create_assignment(
    body: AssignmentCreate,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> AssignmentOut:
    a = AssignmentService(db, school.id).create(
        subject_id=body.subject_id,
        class_id=body.class_id,
        hours_per_week=body.hours_per_week,
        teacher_id=body.teacher_id,
        group_number=body.group_number,
        preferred_classroom_id=body.preferred_classroom_id,
    )
    return AssignmentOut.model_validate(asdict(a))


@router.put("/{assignment_id}", response_model=AssignmentOut)
def update_assignment(
    assignment_id: int,
    body: AssignmentUpdate,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> AssignmentOut:
    a = AssignmentService(db, school.id).update(
        assignment_id,
        subject_id=body.subject_id,
        teacher_id=body.teacher_id,
        class_id=body.class_id,
        hours_per_week=body.hours_per_week,
        group_number=body.group_number,
        preferred_classroom_id=body.preferred_classroom_id,
        clear_teacher=body.clear_teacher,
        clear_group=body.clear_group,
        clear_preferred_classroom=body.clear_preferred_classroom,
    )
    return AssignmentOut.model_validate(asdict(a))


@router.patch("/{assignment_id}/teacher", response_model=AssignmentOut)
def set_teacher(
    assignment_id: int,
    body: AssignTeacherBody,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> AssignmentOut:
    a = AssignmentService(db, school.id).set_teacher(assignment_id, body.teacher_id)
    return AssignmentOut.model_validate(asdict(a))


@router.delete("/{assignment_id}", status_code=204, response_class=Response)
def delete_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> Response:
    AssignmentService(db, school.id).delete(assignment_id)
    return Response(status_code=204)
