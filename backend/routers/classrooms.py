"""Classrooms CRUD API."""
from dataclasses import asdict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.models import School
from app.services.classroom_service import ClassroomService
from backend.deps import get_current_school, get_db
from backend.schemas.classrooms import ClassroomCreate, ClassroomOut, ClassroomUpdate

router = APIRouter()


@router.get("/", response_model=list[ClassroomOut])
def list_classrooms(
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> list[ClassroomOut]:
    return [
        ClassroomOut.model_validate(asdict(c))
        for c in ClassroomService(db, school.id).list()
    ]


@router.get("/{classroom_id}", response_model=ClassroomOut)
def get_classroom(
    classroom_id: int,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> ClassroomOut:
    return ClassroomOut.model_validate(
        asdict(ClassroomService(db, school.id).get(classroom_id))
    )


@router.post("/", response_model=ClassroomOut)
def create_classroom(
    body: ClassroomCreate,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> ClassroomOut:
    c = ClassroomService(db, school.id).create(
        number=body.number,
        name=body.name,
        capacity=body.capacity,
        classes_capacity=body.classes_capacity,
        floor=body.floor,
        building=body.building,
        subject_ids=body.subject_ids,
        is_exclusive=body.is_exclusive,
        teacher_ids=body.teacher_ids,
    )
    return ClassroomOut.model_validate(asdict(c))


@router.put("/{classroom_id}", response_model=ClassroomOut)
def update_classroom(
    classroom_id: int,
    body: ClassroomUpdate,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> ClassroomOut:
    data = body.model_dump(exclude_unset=True)
    c = ClassroomService(db, school.id).update(
        classroom_id,
        number=data.get("number"),
        name=data.get("name"),
        capacity=data.get("capacity"),
        classes_capacity=data.get("classes_capacity"),
        floor=data.get("floor"),
        building=data.get("building"),
        subject_ids=data.get("subject_ids"),
        is_exclusive=data.get("is_exclusive"),
        teacher_ids=data.get("teacher_ids"),
        fields_set=frozenset(data.keys()),
    )
    return ClassroomOut.model_validate(asdict(c))


@router.delete("/{classroom_id}", status_code=204)
def delete_classroom(
    classroom_id: int,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> None:
    ClassroomService(db, school.id).delete(classroom_id)
