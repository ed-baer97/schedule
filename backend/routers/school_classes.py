"""School classes CRUD + batch shift update."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload

from app.models import Classroom, School, SchoolClass, Shift
from backend.deps import get_current_school, get_db, school_owned
from backend.schemas.school_classes import (
    BatchShiftBody,
    SchoolClassCreate,
    SchoolClassOut,
    SchoolClassUpdate,
)

router = APIRouter()


def _grade_from_name(name: str) -> int:
    grade_str = "".join(filter(str.isdigit, name))
    return int(grade_str) if grade_str else 1


def _load_list(db: Session, school_id: int) -> list[SchoolClass]:
    stmt = (
        select(SchoolClass)
        .options(
            joinedload(SchoolClass.shift),
            joinedload(SchoolClass.home_classroom),
        )
        .where(SchoolClass.school_id == school_id)
        .order_by(SchoolClass.grade, SchoolClass.name)
    )
    return list(db.execute(stmt).scalars().unique().all())


@router.get("/", response_model=list[SchoolClassOut])
def list_school_classes(
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> list[SchoolClass]:
    return _load_list(db, school.id)


@router.post("/batch-shift", response_model=list[SchoolClassOut])
def batch_update_shift(
    body: BatchShiftBody,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> list[SchoolClass]:
    if not body.class_ids:
        raise HTTPException(status_code=400, detail="class_ids required")
    if body.shift_id is not None:
        school_owned(db, Shift, body.shift_id, school.id)
    db.execute(
        update(SchoolClass)
        .where(
            SchoolClass.id.in_(body.class_ids),
            SchoolClass.school_id == school.id,
        )
        .values(shift_id=body.shift_id)
    )
    db.commit()
    return _load_list(db, school.id)


@router.get("/{class_id}", response_model=SchoolClassOut)
def get_school_class(
    class_id: int,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> SchoolClass:
    stmt = (
        select(SchoolClass)
        .options(
            joinedload(SchoolClass.shift),
            joinedload(SchoolClass.home_classroom),
        )
        .where(SchoolClass.id == class_id, SchoolClass.school_id == school.id)
    )
    row = db.execute(stmt).scalars().unique().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Class not found")
    return row


@router.post("/", response_model=SchoolClassOut)
def create_school_class(
    body: SchoolClassCreate,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> SchoolClass:
    name = body.name.strip()
    if body.shift_id is not None:
        school_owned(db, Shift, body.shift_id, school.id)
    if body.home_classroom_id is not None:
        school_owned(db, Classroom, body.home_classroom_id, school.id)
    sc = SchoolClass(
        school_id=school.id,
        name=name,
        grade=_grade_from_name(name),
        school_level=body.school_level,
        shift_id=body.shift_id,
        home_classroom_id=body.home_classroom_id,
        students_count=body.students_count,
    )
    db.add(sc)
    db.commit()
    db.refresh(sc)
    return get_school_class(sc.id, db, school)


@router.put("/{class_id}", response_model=SchoolClassOut)
def update_school_class(
    class_id: int,
    body: SchoolClassUpdate,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> SchoolClass:
    sc = school_owned(db, SchoolClass, class_id, school.id)
    data = body.model_dump(exclude_unset=True)
    if "shift_id" in data and data["shift_id"] is not None:
        school_owned(db, Shift, data["shift_id"], school.id)
    if "home_classroom_id" in data and data["home_classroom_id"] is not None:
        school_owned(db, Classroom, data["home_classroom_id"], school.id)
    if "name" in data and data["name"] is not None:
        sc.name = str(data["name"]).strip()
        sc.grade = _grade_from_name(sc.name)
    if "school_level" in data and data["school_level"] is not None:
        sc.school_level = data["school_level"]
    if "shift_id" in data:
        sc.shift_id = data["shift_id"]
    if "home_classroom_id" in data:
        sc.home_classroom_id = data["home_classroom_id"]
    if "students_count" in data:
        sc.students_count = data["students_count"]
    db.commit()
    db.refresh(sc)
    return get_school_class(sc.id, db, school)


@router.delete("/{class_id}", status_code=204)
def delete_school_class(
    class_id: int,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> None:
    sc = school_owned(db, SchoolClass, class_id, school.id)
    db.delete(sc)
    db.commit()
