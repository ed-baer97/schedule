"""Teaching assignments CRUD (teacher↔subject↔class link)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    School,
    Classroom,
    SchoolClass,
    Subject,
    Teacher,
    TeachingAssignment,
)

from backend.deps import get_current_school, get_db, school_owned
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


def _options() -> list:
    return [
        joinedload(TeachingAssignment.subject),
        joinedload(TeachingAssignment.teacher),
        joinedload(TeachingAssignment.school_class),
        joinedload(TeachingAssignment.preferred_classroom),
    ]


@router.get("/", response_model=list[AssignmentOut])
def list_assignments(
    school_level: str | None = Query(None, pattern="^(elementary|secondary)$"),
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> list[AssignmentOut]:
    stmt = (
        select(TeachingAssignment)
        .options(*_options())
        .join(SchoolClass, SchoolClass.id == TeachingAssignment.class_id)
        .where(TeachingAssignment.school_id == school.id)
        .order_by(SchoolClass.grade, SchoolClass.name)
    )
    if school_level:
        stmt = stmt.where(SchoolClass.school_level == school_level)
    rows = db.scalars(stmt).unique().all()
    return [_serialize(a) for a in rows]


@router.get("/{assignment_id}", response_model=AssignmentOut)
def get_assignment(assignment_id: int, db: Session = Depends(get_db),
    school: School = Depends(get_current_school)) -> AssignmentOut:
    stmt = (
        select(TeachingAssignment)
        .options(*_options())
        .where(TeachingAssignment.id == assignment_id, TeachingAssignment.school_id == school.id)
    )
    a = db.execute(stmt).scalars().unique().one_or_none()
    if a is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return _serialize(a)


def _check_refs(
    body: AssignmentCreate | AssignmentUpdate, db: Session, school_id: int
) -> None:
    if body.subject_id is not None:
        school_owned(db, Subject, body.subject_id, school_id)
    if body.class_id is not None:
        school_owned(db, SchoolClass, body.class_id, school_id)
    if body.teacher_id is not None:
        school_owned(db, Teacher, body.teacher_id, school_id)
    if body.preferred_classroom_id is not None:
        school_owned(db, Classroom, body.preferred_classroom_id, school_id)


@router.post("/", response_model=AssignmentOut, status_code=201)
def create_assignment(
    body: AssignmentCreate, db: Session = Depends(get_db),
    school: School = Depends(get_current_school)
) -> AssignmentOut:
    _check_refs(body, db, school.id)
    a = TeachingAssignment(
        school_id=school.id,
        subject_id=body.subject_id,
        teacher_id=body.teacher_id,
        class_id=body.class_id,
        hours_per_week=body.hours_per_week,
        group_number=body.group_number,
        preferred_classroom_id=body.preferred_classroom_id,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return get_assignment(a.id, db, school)


@router.put("/{assignment_id}", response_model=AssignmentOut)
def update_assignment(
    assignment_id: int, body: AssignmentUpdate, db: Session = Depends(get_db),
    school: School = Depends(get_current_school)
) -> AssignmentOut:
    a = school_owned(db, TeachingAssignment, assignment_id, school.id)
    _check_refs(body, db, school.id)
    if body.subject_id is not None:
        a.subject_id = body.subject_id
    if body.class_id is not None:
        a.class_id = body.class_id
    if body.hours_per_week is not None:
        a.hours_per_week = body.hours_per_week
    if body.clear_teacher:
        a.teacher_id = None
    elif body.teacher_id is not None:
        a.teacher_id = body.teacher_id
    if body.clear_group:
        a.group_number = None
    elif body.group_number is not None:
        a.group_number = body.group_number
    if body.clear_preferred_classroom:
        a.preferred_classroom_id = None
    elif body.preferred_classroom_id is not None:
        a.preferred_classroom_id = body.preferred_classroom_id
    db.commit()
    db.refresh(a)
    return get_assignment(a.id, db, school)


@router.patch("/{assignment_id}/teacher", response_model=AssignmentOut)
def set_teacher(
    assignment_id: int, body: AssignTeacherBody, db: Session = Depends(get_db),
    school: School = Depends(get_current_school)
) -> AssignmentOut:
    a = school_owned(db, TeachingAssignment, assignment_id, school.id)
    if body.teacher_id is not None:
        school_owned(db, Teacher, body.teacher_id, school.id)
    a.teacher_id = body.teacher_id
    db.commit()
    db.refresh(a)
    return get_assignment(a.id, db, school)


@router.delete("/{assignment_id}", status_code=204, response_class=Response)
def delete_assignment(assignment_id: int, db: Session = Depends(get_db),
    school: School = Depends(get_current_school)) -> Response:
    a = school_owned(db, TeachingAssignment, assignment_id, school.id)
    db.delete(a)
    db.commit()
    return Response(status_code=204)
