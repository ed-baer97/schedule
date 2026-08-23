"""Teaching assignments CRUD (teacher↔subject↔class link)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.models import School, TeachingAssignment
from app.services.assignment_service import AssignmentService
from app.services.errors import ServiceError
from backend.deps import get_current_school, get_db
from backend.http_errors import raise_http
from backend.schemas.assignments import (
    AssignmentCreate,
    AssignmentOut,
    AssignmentUpdate,
    AssignTeacherBody,
    ClassroomBrief,
    SchoolClassBrief,
    SubjectBrief,
    TeacherBrief,
)

router = APIRouter()


def _serialize(a: TeachingAssignment) -> AssignmentOut:
    return AssignmentOut(
        id=a.id,
        subject_id=a.subject_id,
        teacher_id=a.teacher_id,
        class_id=a.class_id,
        hours_per_week=a.hours_per_week,
        group_number=a.group_number,
        preferred_classroom_id=a.preferred_classroom_id,
        subject=SubjectBrief.model_validate(a.subject),
        teacher=TeacherBrief.model_validate(a.teacher) if a.teacher else None,
        school_class=SchoolClassBrief.model_validate(a.school_class),
        preferred_classroom=(
            ClassroomBrief.model_validate(a.preferred_classroom)
            if a.preferred_classroom
            else None
        ),
    )


@router.get("/", response_model=list[AssignmentOut])
def list_assignments(
    school_level: str | None = Query(None, pattern="^(elementary|secondary)$"),
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> list[AssignmentOut]:
    rows = AssignmentService(db, school.id).list(school_level)
    return [_serialize(a) for a in rows]


@router.get("/{assignment_id}", response_model=AssignmentOut)
def get_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> AssignmentOut:
    try:
        return _serialize(AssignmentService(db, school.id).get(assignment_id))
    except ServiceError as exc:
        raise_http(exc)


@router.post("/", response_model=AssignmentOut, status_code=201)
def create_assignment(
    body: AssignmentCreate,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> AssignmentOut:
    try:
        a = AssignmentService(db, school.id).create(
            subject_id=body.subject_id,
            class_id=body.class_id,
            hours_per_week=body.hours_per_week,
            teacher_id=body.teacher_id,
            group_number=body.group_number,
            preferred_classroom_id=body.preferred_classroom_id,
        )
        return _serialize(a)
    except ServiceError as exc:
        raise_http(exc)


@router.put("/{assignment_id}", response_model=AssignmentOut)
def update_assignment(
    assignment_id: int,
    body: AssignmentUpdate,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> AssignmentOut:
    try:
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
        return _serialize(a)
    except ServiceError as exc:
        raise_http(exc)


@router.patch("/{assignment_id}/teacher", response_model=AssignmentOut)
def set_teacher(
    assignment_id: int,
    body: AssignTeacherBody,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> AssignmentOut:
    try:
        a = AssignmentService(db, school.id).set_teacher(assignment_id, body.teacher_id)
        return _serialize(a)
    except ServiceError as exc:
        raise_http(exc)


@router.delete("/{assignment_id}", status_code=204, response_class=Response)
def delete_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> Response:
    try:
        AssignmentService(db, school.id).delete(assignment_id)
    except ServiceError as exc:
        raise_http(exc)
    return Response(status_code=204)
