"""Classrooms CRUD API."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Classroom, School
from backend.deps import get_current_school, get_db, school_owned
from backend.schemas.classrooms import ClassroomCreate, ClassroomOut, ClassroomUpdate

router = APIRouter()


@router.get("/", response_model=list[ClassroomOut])
def list_classrooms(
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> list[Classroom]:
    stmt = (
        select(Classroom)
        .where(Classroom.school_id == school.id)
        .order_by(func.coalesce(Classroom.floor, 999), Classroom.number)
    )
    return list(db.scalars(stmt).all())


@router.get("/{classroom_id}", response_model=ClassroomOut)
def get_classroom(
    classroom_id: int,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> Classroom:
    return school_owned(db, Classroom, classroom_id, school.id)


@router.post("/", response_model=ClassroomOut)
def create_classroom(
    body: ClassroomCreate,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> Classroom:
    c = Classroom(
        school_id=school.id,
        number=body.number.strip(),
        name=(body.name or "").strip() or None,
        capacity=body.capacity,
        classes_capacity=body.classes_capacity or 1,
        floor=body.floor,
        building=(body.building or "").strip() or None,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@router.put("/{classroom_id}", response_model=ClassroomOut)
def update_classroom(
    classroom_id: int,
    body: ClassroomUpdate,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> Classroom:
    c = school_owned(db, Classroom, classroom_id, school.id)
    data = body.model_dump(exclude_unset=True)
    if "number" in data and data["number"] is not None:
        c.number = str(data["number"]).strip()
    if "name" in data:
        c.name = (data["name"] or "").strip() or None
    if "capacity" in data:
        c.capacity = data["capacity"]
    if "classes_capacity" in data and data["classes_capacity"] is not None:
        c.classes_capacity = int(data["classes_capacity"])
    if "floor" in data:
        c.floor = data["floor"]
    if "building" in data:
        c.building = (data["building"] or "").strip() or None
    db.commit()
    db.refresh(c)
    return c


@router.delete("/{classroom_id}", status_code=204)
def delete_classroom(
    classroom_id: int,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> None:
    c = school_owned(db, Classroom, classroom_id, school.id)
    db.delete(c)
    db.commit()
