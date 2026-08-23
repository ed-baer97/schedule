"""Teachers CRUD API."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.models import School, Teacher
from app.services.errors import ServiceError
from app.services.teacher_service import TeacherService
from backend.deps import get_current_school, get_db
from backend.http_errors import raise_http
from backend.schemas.teachers import TeacherCreate, TeacherOut, TeacherUpdate

router = APIRouter()


@router.get("/", response_model=list[TeacherOut])
def list_teachers(
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> list[Teacher]:
    try:
        return TeacherService(db, school.id).list()
    except ServiceError as exc:
        raise_http(exc)


@router.get("/{teacher_id}", response_model=TeacherOut)
def get_teacher(
    teacher_id: int,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> Teacher:
    try:
        return TeacherService(db, school.id).get(teacher_id)
    except ServiceError as exc:
        raise_http(exc)


@router.post("/", response_model=TeacherOut)
def create_teacher(
    body: TeacherCreate,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> Teacher:
    try:
        return TeacherService(db, school.id).create(
            full_name=body.full_name,
            email=body.email,
            phone=body.phone,
            home_classroom_id=body.home_classroom_id,
        )
    except ServiceError as exc:
        raise_http(exc)


@router.put("/{teacher_id}", response_model=TeacherOut)
def update_teacher(
    teacher_id: int,
    body: TeacherUpdate,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> Teacher:
    data = body.model_dump(exclude_unset=True)
    try:
        return TeacherService(db, school.id).update(
            teacher_id,
            full_name=data.get("full_name"),
            email=data.get("email"),
            phone=data.get("phone"),
            home_classroom_id=data.get("home_classroom_id"),
            fields_set=frozenset(data.keys()),
        )
    except ServiceError as exc:
        raise_http(exc)


@router.delete("/{teacher_id}", status_code=204)
def delete_teacher(
    teacher_id: int,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> None:
    try:
        TeacherService(db, school.id).delete(teacher_id)
    except ServiceError as exc:
        raise_http(exc)
