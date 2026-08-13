"""Subjects CRUD API."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    Classroom,
    ScheduleCell,
    SchoolClass,
    Subject,
    Teacher,
    TeachingAssignment,
)

from backend.deps import get_db
from backend.schemas.subjects import (
    SubjectAssignClassRow,
    SubjectAssignmentsSave,
    SubjectAssignmentsSaveResult,
    SubjectAssignmentsView,
    SubjectAssignTeacherRow,
    SubjectColorOut,
    SubjectColorUpdate,
    SubjectCreate,
    SubjectOut,
    SubjectUpdate,
)

router = APIRouter()


def _list_query(db: Session, school_level: str | None) -> list[Subject]:
    if school_level in ("elementary", "secondary"):
        ids = list(
            db.scalars(
                select(TeachingAssignment.subject_id)
                .join(SchoolClass, SchoolClass.id == TeachingAssignment.class_id)
                .where(SchoolClass.school_level == school_level)
                .distinct()
            ).all()
        )
        if not ids:
            return []
        stmt = (
            select(Subject)
            .where(Subject.id.in_(ids))
            .options(joinedload(Subject.default_classroom))
            .order_by(Subject.name)
        )
        rows = db.scalars(stmt).unique().all()
        return list(rows)
    stmt = (
        select(Subject)
        .options(joinedload(Subject.default_classroom))
        .order_by(Subject.name)
    )
    return list(db.scalars(stmt).unique().all())


@router.get("/", response_model=list[SubjectOut])
def list_subjects(
    db: Session = Depends(get_db),
    school_level: str | None = Query(None, pattern="^(elementary|secondary)$"),
) -> list[Subject]:
    return _list_query(db, school_level)


@router.get("/meta/color-palette", response_model=list[str])
def color_palette() -> list[str]:
    return list(Subject.COLOR_PALETTE)


@router.get("/{subject_id}", response_model=SubjectOut)
def get_subject(subject_id: int, db: Session = Depends(get_db)) -> Subject:
    stmt = (
        select(Subject)
        .options(joinedload(Subject.default_classroom))
        .where(Subject.id == subject_id)
    )
    row = db.execute(stmt).scalars().unique().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Subject not found")
    return row


@router.post("/", response_model=SubjectOut)
def create_subject(body: SubjectCreate, db: Session = Depends(get_db)) -> Subject:
    if body.default_classroom_id is not None:
        if db.get(Classroom, body.default_classroom_id) is None:
            raise HTTPException(status_code=400, detail="default_classroom not found")
    s = Subject(
        name=body.name.strip(),
        color=body.color,
        requires_fixed_classroom=body.requires_fixed_classroom,
        default_classroom_id=body.default_classroom_id,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return get_subject(s.id, db)


@router.put("/{subject_id}", response_model=SubjectOut)
def update_subject(
    subject_id: int, body: SubjectUpdate, db: Session = Depends(get_db)
) -> Subject:
    s = db.get(Subject, subject_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Subject not found")
    data = body.model_dump(exclude_unset=True)
    if "default_classroom_id" in data and data["default_classroom_id"] is not None:
        if db.get(Classroom, data["default_classroom_id"]) is None:
            raise HTTPException(status_code=400, detail="default_classroom not found")
    if "name" in data and data["name"] is not None:
        s.name = str(data["name"]).strip()
    if "color" in data and data["color"] is not None:
        s.color = data["color"]
    if "requires_fixed_classroom" in data and data["requires_fixed_classroom"] is not None:
        s.requires_fixed_classroom = bool(data["requires_fixed_classroom"])
    if "default_classroom_id" in data:
        s.default_classroom_id = data["default_classroom_id"]
    db.commit()
    db.refresh(s)
    return get_subject(s.id, db)


@router.patch("/{subject_id}/color", response_model=SubjectColorOut)
def set_subject_color(
    subject_id: int, body: SubjectColorUpdate, db: Session = Depends(get_db)
) -> SubjectColorOut:
    """Quick color change from the subjects list."""
    s = db.get(Subject, subject_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Subject not found")
    s.color = body.color
    db.commit()
    db.refresh(s)
    return SubjectColorOut(id=s.id, display_color=s.display_color)


@router.delete("/{subject_id}", status_code=204)
def delete_subject(subject_id: int, db: Session = Depends(get_db)) -> None:
    s = db.get(Subject, subject_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Subject not found")
    db.delete(s)
    db.commit()


def _reassign_cells_and_delete_assignment(
    db: Session, assignment: TeachingAssignment, target_assignment_id: int
) -> None:
    """Move schedule cells to another assignment, flush, then delete (avoids FK NULL on delete)."""
    cells = (
        db.scalars(
            select(ScheduleCell).where(ScheduleCell.assignment_id == assignment.id)
        )
        .all()
    )
    for cell in cells:
        cell.assignment_id = target_assignment_id
    if cells:
        db.flush()
    db.delete(assignment)


@router.get("/{subject_id}/assignments", response_model=SubjectAssignmentsView)
def get_subject_assignments(
    subject_id: int,
    school_level: str = Query("elementary", pattern="^(elementary|secondary)$"),
    db: Session = Depends(get_db),
) -> SubjectAssignmentsView:
    subject = db.execute(
        select(Subject)
        .options(joinedload(Subject.default_classroom))
        .where(Subject.id == subject_id)
    ).scalars().unique().one_or_none()
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found")

    class_ids = list(
        db.scalars(
            select(TeachingAssignment.class_id)
            .join(SchoolClass, SchoolClass.id == TeachingAssignment.class_id)
            .where(
                TeachingAssignment.subject_id == subject.id,
                SchoolClass.school_level == school_level,
            )
            .distinct()
        ).all()
    )
    classes = (
        list(
            db.scalars(
                select(SchoolClass)
                .where(SchoolClass.id.in_(class_ids))
                .order_by(SchoolClass.grade, SchoolClass.name)
            ).all()
        )
        if class_ids
        else []
    )

    assignments = (
        list(
            db.scalars(
                select(TeachingAssignment)
                .join(SchoolClass, SchoolClass.id == TeachingAssignment.class_id)
                .where(
                    TeachingAssignment.subject_id == subject.id,
                    SchoolClass.school_level == school_level,
                )
            ).all()
        )
        if class_ids
        else []
    )

    class_teachers: dict[int, set[int]] = {}
    class_hours: dict[int, int] = {}
    split_class_ids: set[int] = set()
    for a in assignments:
        class_teachers.setdefault(a.class_id, set())
        if a.teacher_id:
            class_teachers[a.class_id].add(a.teacher_id)
        if a.group_number is not None:
            split_class_ids.add(a.class_id)
        class_hours.setdefault(a.class_id, a.hours_per_week)

    class_rows = [
        SubjectAssignClassRow(
            id=c.id,
            name=c.name,
            grade=c.grade,
            hours_per_week=class_hours.get(c.id, 0),
            teacher_ids=sorted(class_teachers.get(c.id, set())),
            is_split=c.id in split_class_ids,
        )
        for c in classes
    ]

    attached_ids = list(
        db.scalars(
            select(TeachingAssignment.teacher_id)
            .where(
                TeachingAssignment.subject_id == subject.id,
                TeachingAssignment.teacher_id.isnot(None),
            )
            .distinct()
        ).all()
    )
    attached_teachers = (
        list(
            db.scalars(
                select(Teacher)
                .where(Teacher.id.in_(attached_ids))
                .order_by(Teacher.full_name)
            ).all()
        )
        if attached_ids
        else []
    )
    all_teachers = list(
        db.scalars(select(Teacher).order_by(Teacher.full_name)).all()
    )

    return SubjectAssignmentsView(
        subject=SubjectOut.model_validate(subject),
        school_level=school_level,
        classes=class_rows,
        attached_teachers=[
            SubjectAssignTeacherRow(id=t.id, full_name=t.full_name) for t in attached_teachers
        ],
        all_teachers=[
            SubjectAssignTeacherRow(id=t.id, full_name=t.full_name) for t in all_teachers
        ],
    )


@router.post(
    "/{subject_id}/assignments", response_model=SubjectAssignmentsSaveResult
)
def save_subject_assignments(
    subject_id: int,
    body: SubjectAssignmentsSave,
    db: Session = Depends(get_db),
) -> SubjectAssignmentsSaveResult:
    subject = db.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found")

    class_ids = list(
        db.scalars(
            select(TeachingAssignment.class_id)
            .join(SchoolClass, SchoolClass.id == TeachingAssignment.class_id)
            .where(
                TeachingAssignment.subject_id == subject.id,
                SchoolClass.school_level == body.school_level,
            )
            .distinct()
        ).all()
    )
    if not class_ids:
        return SubjectAssignmentsSaveResult(ok=True, errors=[])

    classes = list(
        db.scalars(
            select(SchoolClass).where(SchoolClass.id.in_(class_ids))
        ).all()
    )
    allowed_teacher_ids = set(body.teacher_ids)
    errors: list[str] = []

    for school_class in classes:
        raw = body.selections.get(str(school_class.id), [])
        checked_teachers = [tid for tid in raw if tid in allowed_teacher_ids]
        if len(checked_teachers) > 2:
            errors.append(
                f"Класс {school_class.name}: максимум 2 учителя на один предмет"
            )
            continue

        existing = list(
            db.scalars(
                select(TeachingAssignment)
                .where(
                    TeachingAssignment.subject_id == subject.id,
                    TeachingAssignment.class_id == school_class.id,
                )
                .order_by(TeachingAssignment.group_number)
            ).all()
        )
        if not existing:
            continue

        hours = existing[0].hours_per_week

        if len(checked_teachers) == 0:
            for i, a in enumerate(existing):
                if i == 0:
                    a.teacher_id = None
                    a.group_number = None
                else:
                    _reassign_cells_and_delete_assignment(db, a, existing[0].id)
        elif len(checked_teachers) == 1:
            for i, a in enumerate(existing):
                if i == 0:
                    a.teacher_id = checked_teachers[0]
                    a.group_number = None
                else:
                    _reassign_cells_and_delete_assignment(db, a, existing[0].id)
        else:
            if len(existing) >= 2:
                existing[0].teacher_id = checked_teachers[0]
                existing[0].group_number = 1
                existing[1].teacher_id = checked_teachers[1]
                existing[1].group_number = 2
                for a in existing[2:]:
                    _reassign_cells_and_delete_assignment(db, a, existing[0].id)
            else:
                existing[0].teacher_id = checked_teachers[0]
                existing[0].group_number = 1
                db.add(
                    TeachingAssignment(
                        subject_id=subject.id,
                        class_id=school_class.id,
                        teacher_id=checked_teachers[1],
                        hours_per_week=hours,
                        group_number=2,
                    )
                )

    if errors:
        db.rollback()
        return SubjectAssignmentsSaveResult(ok=False, errors=errors)
    db.commit()
    return SubjectAssignmentsSaveResult(ok=True, errors=[])
