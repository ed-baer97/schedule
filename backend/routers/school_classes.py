"""School classes CRUD + batch shift update."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.models import School, SchoolClass
from app.services.errors import ServiceError
from app.services.school_class_service import SchoolClassService
from backend.deps import get_current_school, get_db
from backend.http_errors import raise_http
from backend.schemas.school_classes import (
    BatchShiftBody,
    SchoolClassCreate,
    SchoolClassOut,
    SchoolClassUpdate,
)

router = APIRouter()


@router.get("/", response_model=list[SchoolClassOut])
def list_school_classes(
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> list[SchoolClass]:
    try:
        return SchoolClassService(db, school.id).list()
    except ServiceError as exc:
        raise_http(exc)


@router.post("/batch-shift", response_model=list[SchoolClassOut])
def batch_update_shift(
    body: BatchShiftBody,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> list[SchoolClass]:
    try:
        return SchoolClassService(db, school.id).batch_update_shift(
            body.class_ids, body.shift_id
        )
    except ServiceError as exc:
        raise_http(exc)


@router.get("/{class_id}", response_model=SchoolClassOut)
def get_school_class(
    class_id: int,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> SchoolClass:
    try:
        return SchoolClassService(db, school.id).get(class_id)
    except ServiceError as exc:
        raise_http(exc)


@router.post("/", response_model=SchoolClassOut)
def create_school_class(
    body: SchoolClassCreate,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> SchoolClass:
    try:
        return SchoolClassService(db, school.id).create(
            name=body.name,
            school_level=body.school_level,
            shift_id=body.shift_id,
            home_classroom_id=body.home_classroom_id,
            students_count=body.students_count,
        )
    except ServiceError as exc:
        raise_http(exc)


@router.put("/{class_id}", response_model=SchoolClassOut)
def update_school_class(
    class_id: int,
    body: SchoolClassUpdate,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> SchoolClass:
    data = body.model_dump(exclude_unset=True)
    try:
        return SchoolClassService(db, school.id).update(
            class_id,
            name=data.get("name"),
            school_level=data.get("school_level"),
            shift_id=data.get("shift_id"),
            home_classroom_id=data.get("home_classroom_id"),
            students_count=data.get("students_count"),
            fields_set=frozenset(data.keys()),
        )
    except ServiceError as exc:
        raise_http(exc)


@router.delete("/{class_id}", status_code=204)
def delete_school_class(
    class_id: int,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> None:
    try:
        SchoolClassService(db, school.id).delete(class_id)
    except ServiceError as exc:
        raise_http(exc)
