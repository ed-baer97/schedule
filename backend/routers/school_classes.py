"""School classes CRUD + batch shift update."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload

from app.models import SchoolClass, Shift

from backend.deps import get_db
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


def _load_list(db: Session) -> list[SchoolClass]:
    stmt = (
        select(SchoolClass)
        .options(
            joinedload(SchoolClass.shift),
            joinedload(SchoolClass.home_classroom),
        )
        .order_by(SchoolClass.grade, SchoolClass.name)
    )
    return list(db.execute(stmt).scalars().unique().all())


@router.get("/", response_model=list[SchoolClassOut])
def list_school_classes(db: Session = Depends(get_db)) -> list[SchoolClass]:
    return _load_list(db)


@router.post("/batch-shift", response_model=list[SchoolClassOut])
def batch_update_shift(body: BatchShiftBody, db: Session = Depends(get_db)) -> list[SchoolClass]:
    if not body.class_ids:
        raise HTTPException(status_code=400, detail="class_ids required")
    if body.shift_id is not None and db.get(Shift, body.shift_id) is None:
        raise HTTPException(status_code=400, detail="Shift not found")
    db.execute(
        update(SchoolClass)
        .where(SchoolClass.id.in_(body.class_ids))
        .values(shift_id=body.shift_id)
    )
    db.commit()
    return _load_list(db)


@router.get("/{class_id}", response_model=SchoolClassOut)
def get_school_class(class_id: int, db: Session = Depends(get_db)) -> SchoolClass:
    stmt = (
        select(SchoolClass)
        .options(
            joinedload(SchoolClass.shift),
            joinedload(SchoolClass.home_classroom),
        )
        .where(SchoolClass.id == class_id)
    )
    row = db.execute(stmt).scalars().unique().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Class not found")
    return row


@router.post("/", response_model=SchoolClassOut)
def create_school_class(body: SchoolClassCreate, db: Session = Depends(get_db)) -> SchoolClass:
    name = body.name.strip()
    if body.shift_id is not None and db.get(Shift, body.shift_id) is None:
        raise HTTPException(status_code=400, detail="Shift not found")
    sc = SchoolClass(
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
    return get_school_class(sc.id, db)


@router.put("/{class_id}", response_model=SchoolClassOut)
def update_school_class(
    class_id: int, body: SchoolClassUpdate, db: Session = Depends(get_db)
) -> SchoolClass:
    sc = db.get(SchoolClass, class_id)
    if sc is None:
        raise HTTPException(status_code=404, detail="Class not found")
    data = body.model_dump(exclude_unset=True)
    if "shift_id" in data and data["shift_id"] is not None:
        if db.get(Shift, data["shift_id"]) is None:
            raise HTTPException(status_code=400, detail="Shift not found")
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
    return get_school_class(sc.id, db)


@router.delete("/{class_id}", status_code=204)
def delete_school_class(class_id: int, db: Session = Depends(get_db)) -> None:
    sc = db.get(SchoolClass, class_id)
    if sc is None:
        raise HTTPException(status_code=404, detail="Class not found")
    db.delete(sc)
    db.commit()
