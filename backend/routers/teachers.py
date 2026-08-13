"""Teachers CRUD API."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Classroom, Teacher

from backend.deps import get_db
from backend.schemas.teachers import TeacherCreate, TeacherOut, TeacherUpdate

router = APIRouter()


@router.get("/", response_model=list[TeacherOut])
def list_teachers(db: Session = Depends(get_db)) -> list[Teacher]:
    stmt = (
        select(Teacher)
        .options(joinedload(Teacher.home_classroom))
        .order_by(Teacher.full_name)
    )
    result = db.execute(stmt)
    return list(result.scalars().unique().all())


@router.get("/{teacher_id}", response_model=TeacherOut)
def get_teacher(teacher_id: int, db: Session = Depends(get_db)) -> Teacher:
    stmt = (
        select(Teacher)
        .options(joinedload(Teacher.home_classroom))
        .where(Teacher.id == teacher_id)
    )
    result = db.execute(stmt)
    teacher = result.scalars().unique().one_or_none()
    if teacher is None:
        raise HTTPException(status_code=404, detail="Teacher not found")
    return teacher


@router.post("/", response_model=TeacherOut)
def create_teacher(body: TeacherCreate, db: Session = Depends(get_db)) -> Teacher:
    if body.home_classroom_id is not None:
        if db.get(Classroom, body.home_classroom_id) is None:
            raise HTTPException(status_code=400, detail="home_classroom not found")
    t = Teacher(
        full_name=body.full_name.strip(),
        email=(body.email or "").strip() or None,
        phone=(body.phone or "").strip() or None,
        home_classroom_id=body.home_classroom_id,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return get_teacher(t.id, db)


@router.put("/{teacher_id}", response_model=TeacherOut)
def update_teacher(
    teacher_id: int, body: TeacherUpdate, db: Session = Depends(get_db)
) -> Teacher:
    t = db.get(Teacher, teacher_id)
    if t is None:
        raise HTTPException(status_code=404, detail="Teacher not found")
    data = body.model_dump(exclude_unset=True)
    if "home_classroom_id" in data and data["home_classroom_id"] is not None:
        if db.get(Classroom, data["home_classroom_id"]) is None:
            raise HTTPException(status_code=400, detail="home_classroom not found")
    if "full_name" in data and data["full_name"] is not None:
        t.full_name = str(data["full_name"]).strip()
    if "email" in data:
        raw = data["email"]
        t.email = None if raw in (None, "") else str(raw).strip() or None
    if "phone" in data:
        raw = data["phone"]
        t.phone = None if raw in (None, "") else str(raw).strip() or None
    if "home_classroom_id" in data:
        t.home_classroom_id = data["home_classroom_id"]
    db.commit()
    db.refresh(t)
    return get_teacher(t.id, db)


@router.delete("/{teacher_id}", status_code=204)
def delete_teacher(teacher_id: int, db: Session = Depends(get_db)) -> None:
    t = db.get(Teacher, teacher_id)
    if t is None:
        raise HTTPException(status_code=404, detail="Teacher not found")
    db.delete(t)
    db.commit()
