"""Workload (hours per class x subject) API."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SchoolClass, Subject, TeachingAssignment

from backend.deps import get_db
from backend.schemas.workload import (
    SchoolClassBrief,
    SubjectBrief,
    WorkloadCellOut,
    WorkloadCellUpdate,
    WorkloadOut,
)

router = APIRouter()


@router.get("/", response_model=WorkloadOut)
def get_workload(
    db: Session = Depends(get_db),
    school_level: str = Query("elementary", pattern="^(elementary|secondary)$"),
) -> WorkloadOut:
    classes = list(
        db.scalars(
            select(SchoolClass)
            .where(SchoolClass.school_level == school_level)
            .order_by(SchoolClass.grade, SchoolClass.name)
        ).all()
    )
    subjects = list(db.scalars(select(Subject).order_by(Subject.name)).all())
    assignments = list(
        db.scalars(
            select(TeachingAssignment)
            .join(SchoolClass, SchoolClass.id == TeachingAssignment.class_id)
            .where(SchoolClass.school_level == school_level)
        ).all()
    )
    totals: dict[tuple[int, int], int] = {}
    for a in assignments:
        key = (a.class_id, a.subject_id)
        totals[key] = totals.get(key, 0) + int(a.hours_per_week or 0)
    cells = [
        WorkloadCellOut(class_id=k[0], subject_id=k[1], hours=h)
        for k, h in sorted(totals.items())
    ]
    return WorkloadOut(
        school_level=school_level,
        classes=[SchoolClassBrief.model_validate(c) for c in classes],
        subjects=[SubjectBrief.model_validate(s) for s in subjects],
        cells=cells,
    )


@router.put("/cell", response_model=dict)
def update_workload_cell(body: WorkloadCellUpdate, db: Session = Depends(get_db)) -> dict:
    if body.hours < 0:
        raise HTTPException(status_code=400, detail="hours must be >= 0")
    if db.get(SchoolClass, body.class_id) is None:
        raise HTTPException(status_code=400, detail="class not found")
    if db.get(Subject, body.subject_id) is None:
        raise HTTPException(status_code=400, detail="subject not found")

    assignment = db.scalars(
        select(TeachingAssignment).where(
            TeachingAssignment.class_id == body.class_id,
            TeachingAssignment.subject_id == body.subject_id,
            TeachingAssignment.teacher_id.is_(None),
        )
    ).first()

    if body.hours == 0:
        if assignment:
            db.delete(assignment)
            db.commit()
        return {"status": "ok"}

    if assignment:
        assignment.hours_per_week = body.hours
    else:
        db.add(
            TeachingAssignment(
                class_id=body.class_id,
                subject_id=body.subject_id,
                hours_per_week=body.hours,
                teacher_id=None,
            )
        )
    db.commit()
    return {"status": "ok"}
