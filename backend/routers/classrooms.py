"""Classrooms CRUD API."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.models import Classroom, School
from app.services.classroom_service import ClassroomService
from app.services.errors import ServiceError
from backend.deps import get_current_school, get_db
from backend.http_errors import raise_http
from backend.schemas.classrooms import ClassroomCreate, ClassroomOut, ClassroomUpdate

router = APIRouter()


@router.get("/", response_model=list[ClassroomOut])
def list_classrooms(
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> list[Classroom]:
    try:
        return ClassroomService(db, school.id).list()
    except ServiceError as exc:
        raise_http(exc)


@router.get("/{classroom_id}", response_model=ClassroomOut)
def get_classroom(
    classroom_id: int,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> Classroom:
    try:
        return ClassroomService(db, school.id).get(classroom_id)
    except ServiceError as exc:
        raise_http(exc)


@router.post("/", response_model=ClassroomOut)
def create_classroom(
    body: ClassroomCreate,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> Classroom:
    try:
        return ClassroomService(db, school.id).create(
            number=body.number,
            name=body.name,
            capacity=body.capacity,
            classes_capacity=body.classes_capacity,
            floor=body.floor,
            building=body.building,
        )
    except ServiceError as exc:
        raise_http(exc)


@router.put("/{classroom_id}", response_model=ClassroomOut)
def update_classroom(
    classroom_id: int,
    body: ClassroomUpdate,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> Classroom:
    data = body.model_dump(exclude_unset=True)
    try:
        return ClassroomService(db, school.id).update(
            classroom_id,
            number=data.get("number"),
            name=data.get("name"),
            capacity=data.get("capacity"),
            classes_capacity=data.get("classes_capacity"),
            floor=data.get("floor"),
            building=data.get("building"),
            fields_set=frozenset(data.keys()),
        )
    except ServiceError as exc:
        raise_http(exc)


@router.delete("/{classroom_id}", status_code=204)
def delete_classroom(
    classroom_id: int,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> None:
    try:
        ClassroomService(db, school.id).delete(classroom_id)
    except ServiceError as exc:
        raise_http(exc)
