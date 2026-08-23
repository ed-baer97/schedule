"""Teaching assignment use-cases (CRUD, subject matrix, workload hours)."""
from __future__ import annotations

from dataclasses import dataclass, field

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
from app.services.errors import BadRequestError, NotFoundError
from app.services.tenancy import require_owned


@dataclass
class SubjectAssignClassData:
    id: int
    name: str
    grade: int
    hours_per_week: int
    teacher_ids: list[int]
    is_split: bool


@dataclass
class SubjectAssignTeacherData:
    id: int
    full_name: str


@dataclass
class SubjectAssignmentsViewData:
    subject: Subject
    school_level: str
    classes: list[SubjectAssignClassData]
    attached_teachers: list[SubjectAssignTeacherData]
    all_teachers: list[SubjectAssignTeacherData]


@dataclass
class SubjectAssignmentsSaveResultData:
    ok: bool
    errors: list[str] = field(default_factory=list)


@dataclass
class WorkloadViewData:
    school_level: str
    classes: list[SchoolClass]
    subjects: list[Subject]
    cells: list[tuple[int, int, int]]  # class_id, subject_id, hours


class AssignmentService:
    def __init__(self, db: Session, school_id: int):
        self.db = db
        self.school_id = school_id

    @staticmethod
    def _load_options() -> list:
        return [
            joinedload(TeachingAssignment.subject),
            joinedload(TeachingAssignment.teacher),
            joinedload(TeachingAssignment.school_class),
            joinedload(TeachingAssignment.preferred_classroom),
        ]

    def list(self, school_level: str | None = None) -> list[TeachingAssignment]:
        stmt = (
            select(TeachingAssignment)
            .options(*self._load_options())
            .join(SchoolClass, SchoolClass.id == TeachingAssignment.class_id)
            .where(TeachingAssignment.school_id == self.school_id)
            .order_by(SchoolClass.grade, SchoolClass.name)
        )
        if school_level:
            stmt = stmt.where(SchoolClass.school_level == school_level)
        return list(self.db.scalars(stmt).unique().all())

    def get(self, assignment_id: int) -> TeachingAssignment:
        stmt = (
            select(TeachingAssignment)
            .options(*self._load_options())
            .where(
                TeachingAssignment.id == assignment_id,
                TeachingAssignment.school_id == self.school_id,
            )
        )
        a = self.db.execute(stmt).scalars().unique().one_or_none()
        if a is None:
            raise NotFoundError("Assignment not found")
        return a

    def _check_refs(
        self,
        *,
        subject_id: int | None = None,
        class_id: int | None = None,
        teacher_id: int | None = None,
        preferred_classroom_id: int | None = None,
    ) -> None:
        if subject_id is not None:
            require_owned(self.db, Subject, subject_id, self.school_id)
        if class_id is not None:
            require_owned(self.db, SchoolClass, class_id, self.school_id)
        if teacher_id is not None:
            require_owned(self.db, Teacher, teacher_id, self.school_id)
        if preferred_classroom_id is not None:
            require_owned(self.db, Classroom, preferred_classroom_id, self.school_id)

    def create(
        self,
        *,
        subject_id: int,
        class_id: int,
        hours_per_week: int,
        teacher_id: int | None = None,
        group_number: int | None = None,
        preferred_classroom_id: int | None = None,
        commit: bool = True,
    ) -> TeachingAssignment:
        self._check_refs(
            subject_id=subject_id,
            class_id=class_id,
            teacher_id=teacher_id,
            preferred_classroom_id=preferred_classroom_id,
        )
        a = TeachingAssignment(
            school_id=self.school_id,
            subject_id=subject_id,
            teacher_id=teacher_id,
            class_id=class_id,
            hours_per_week=hours_per_week,
            group_number=group_number,
            preferred_classroom_id=preferred_classroom_id,
        )
        self.db.add(a)
        if commit:
            self.db.commit()
            return self.get(a.id)
        self.db.flush()
        return a

    def upsert_hours(
        self,
        *,
        subject_id: int,
        class_id: int,
        hours_per_week: int,
        teacher_id: int | None = None,
        match_null_teacher: bool = False,
        group_number: int | None = None,
        set_group: bool = False,
        commit: bool = False,
    ) -> tuple[TeachingAssignment, bool]:
        """Create or update hours for an assignment (import write-path)."""
        stmt = select(TeachingAssignment).where(
            TeachingAssignment.school_id == self.school_id,
            TeachingAssignment.subject_id == subject_id,
            TeachingAssignment.class_id == class_id,
        )
        if match_null_teacher:
            stmt = stmt.where(
                TeachingAssignment.teacher_id.is_(None),
                TeachingAssignment.group_number.is_(None),
            )
        else:
            stmt = stmt.where(TeachingAssignment.teacher_id == teacher_id)
        existing = self.db.scalars(stmt).first()
        if existing is not None:
            existing.hours_per_week = hours_per_week
            if set_group:
                existing.group_number = group_number
            if commit:
                self.db.commit()
            else:
                self.db.flush()
            return existing, False
        created = self.create(
            subject_id=subject_id,
            class_id=class_id,
            hours_per_week=hours_per_week,
            teacher_id=teacher_id,
            group_number=group_number if set_group else None,
            commit=commit,
        )
        return created, True

    def update(
        self,
        assignment_id: int,
        *,
        subject_id: int | None = None,
        teacher_id: int | None = None,
        class_id: int | None = None,
        hours_per_week: int | None = None,
        group_number: int | None = None,
        preferred_classroom_id: int | None = None,
        clear_teacher: bool = False,
        clear_group: bool = False,
        clear_preferred_classroom: bool = False,
    ) -> TeachingAssignment:
        a = require_owned(self.db, TeachingAssignment, assignment_id, self.school_id)
        self._check_refs(
            subject_id=subject_id,
            class_id=class_id,
            teacher_id=teacher_id,
            preferred_classroom_id=preferred_classroom_id,
        )
        if subject_id is not None:
            a.subject_id = subject_id
        if class_id is not None:
            a.class_id = class_id
        if hours_per_week is not None:
            a.hours_per_week = hours_per_week
        if clear_teacher:
            a.teacher_id = None
        elif teacher_id is not None:
            a.teacher_id = teacher_id
        if clear_group:
            a.group_number = None
        elif group_number is not None:
            a.group_number = group_number
        if clear_preferred_classroom:
            a.preferred_classroom_id = None
        elif preferred_classroom_id is not None:
            a.preferred_classroom_id = preferred_classroom_id
        self.db.commit()
        return self.get(a.id)

    def set_teacher(
        self, assignment_id: int, teacher_id: int | None
    ) -> TeachingAssignment:
        a = require_owned(self.db, TeachingAssignment, assignment_id, self.school_id)
        if teacher_id is not None:
            require_owned(self.db, Teacher, teacher_id, self.school_id)
        a.teacher_id = teacher_id
        self.db.commit()
        return self.get(a.id)

    def delete(self, assignment_id: int) -> None:
        a = require_owned(self.db, TeachingAssignment, assignment_id, self.school_id)
        self.db.delete(a)
        self.db.commit()

    def _reassign_cells_and_delete(
        self, assignment: TeachingAssignment, target_assignment_id: int
    ) -> None:
        cells = list(
            self.db.scalars(
                select(ScheduleCell).where(ScheduleCell.assignment_id == assignment.id)
            ).all()
        )
        for cell in cells:
            cell.assignment_id = target_assignment_id
        if cells:
            self.db.flush()
        self.db.delete(assignment)

    def get_subject_assignments(
        self, subject_id: int, school_level: str
    ) -> SubjectAssignmentsViewData:
        subject = self.db.execute(
            select(Subject)
            .options(joinedload(Subject.default_classroom))
            .where(Subject.id == subject_id, Subject.school_id == self.school_id)
        ).scalars().unique().one_or_none()
        if subject is None:
            raise NotFoundError("Subject not found")

        class_ids = list(
            self.db.scalars(
                select(TeachingAssignment.class_id)
                .join(SchoolClass, SchoolClass.id == TeachingAssignment.class_id)
                .where(
                    TeachingAssignment.subject_id == subject.id,
                    TeachingAssignment.school_id == self.school_id,
                    SchoolClass.school_level == school_level,
                )
                .distinct()
            ).all()
        )
        classes = (
            list(
                self.db.scalars(
                    select(SchoolClass)
                    .where(
                        SchoolClass.id.in_(class_ids),
                        SchoolClass.school_id == self.school_id,
                    )
                    .order_by(SchoolClass.grade, SchoolClass.name)
                ).all()
            )
            if class_ids
            else []
        )
        assignments = (
            list(
                self.db.scalars(
                    select(TeachingAssignment)
                    .join(SchoolClass, SchoolClass.id == TeachingAssignment.class_id)
                    .where(
                        TeachingAssignment.subject_id == subject.id,
                        TeachingAssignment.school_id == self.school_id,
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
            SubjectAssignClassData(
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
            self.db.scalars(
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
                self.db.scalars(
                    select(Teacher)
                    .where(
                        Teacher.id.in_(attached_ids),
                        Teacher.school_id == self.school_id,
                    )
                    .order_by(Teacher.full_name)
                ).all()
            )
            if attached_ids
            else []
        )
        all_teachers = list(
            self.db.scalars(
                select(Teacher)
                .where(Teacher.school_id == self.school_id)
                .order_by(Teacher.full_name)
            ).all()
        )

        return SubjectAssignmentsViewData(
            subject=subject,
            school_level=school_level,
            classes=class_rows,
            attached_teachers=[
                SubjectAssignTeacherData(id=t.id, full_name=t.full_name)
                for t in attached_teachers
            ],
            all_teachers=[
                SubjectAssignTeacherData(id=t.id, full_name=t.full_name)
                for t in all_teachers
            ],
        )

    def save_subject_assignments(
        self,
        subject_id: int,
        *,
        school_level: str,
        teacher_ids: list[int],
        selections: dict[str, list[int]],
    ) -> SubjectAssignmentsSaveResultData:
        subject = require_owned(self.db, Subject, subject_id, self.school_id)

        class_ids = list(
            self.db.scalars(
                select(TeachingAssignment.class_id)
                .join(SchoolClass, SchoolClass.id == TeachingAssignment.class_id)
                .where(
                    TeachingAssignment.subject_id == subject.id,
                    TeachingAssignment.school_id == self.school_id,
                    SchoolClass.school_level == school_level,
                )
                .distinct()
            ).all()
        )
        if not class_ids:
            return SubjectAssignmentsSaveResultData(ok=True, errors=[])

        classes = list(
            self.db.scalars(
                select(SchoolClass).where(
                    SchoolClass.id.in_(class_ids),
                    SchoolClass.school_id == self.school_id,
                )
            ).all()
        )
        allowed_teacher_ids = set(teacher_ids)
        errors: list[str] = []

        for school_class in classes:
            raw = selections.get(str(school_class.id), [])
            checked_teachers = [tid for tid in raw if tid in allowed_teacher_ids]
            if len(checked_teachers) > 2:
                errors.append(
                    f"Класс {school_class.name}: максимум 2 учителя на один предмет"
                )
                continue

            existing = list(
                self.db.scalars(
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
                        self._reassign_cells_and_delete(a, existing[0].id)
            elif len(checked_teachers) == 1:
                for i, a in enumerate(existing):
                    if i == 0:
                        a.teacher_id = checked_teachers[0]
                        a.group_number = None
                    else:
                        self._reassign_cells_and_delete(a, existing[0].id)
            else:
                if len(existing) >= 2:
                    existing[0].teacher_id = checked_teachers[0]
                    existing[0].group_number = 1
                    existing[1].teacher_id = checked_teachers[1]
                    existing[1].group_number = 2
                    for a in existing[2:]:
                        self._reassign_cells_and_delete(a, existing[0].id)
                else:
                    existing[0].teacher_id = checked_teachers[0]
                    existing[0].group_number = 1
                    self.db.add(
                        TeachingAssignment(
                            school_id=self.school_id,
                            subject_id=subject.id,
                            class_id=school_class.id,
                            teacher_id=checked_teachers[1],
                            hours_per_week=hours,
                            group_number=2,
                        )
                    )

        if errors:
            self.db.rollback()
            return SubjectAssignmentsSaveResultData(ok=False, errors=errors)
        self.db.commit()
        return SubjectAssignmentsSaveResultData(ok=True, errors=[])

    def get_workload(self, school_level: str) -> WorkloadViewData:
        classes = list(
            self.db.scalars(
                select(SchoolClass)
                .where(
                    SchoolClass.school_id == self.school_id,
                    SchoolClass.school_level == school_level,
                )
                .order_by(SchoolClass.grade, SchoolClass.name)
            ).all()
        )
        subjects = list(
            self.db.scalars(
                select(Subject)
                .where(Subject.school_id == self.school_id)
                .order_by(Subject.name)
            ).all()
        )
        assignments = list(
            self.db.scalars(
                select(TeachingAssignment)
                .join(SchoolClass, SchoolClass.id == TeachingAssignment.class_id)
                .where(
                    TeachingAssignment.school_id == self.school_id,
                    SchoolClass.school_level == school_level,
                )
            ).all()
        )
        totals: dict[tuple[int, int], int] = {}
        for a in assignments:
            key = (a.class_id, a.subject_id)
            totals[key] = totals.get(key, 0) + int(a.hours_per_week or 0)
        cells = [(k[0], k[1], h) for k, h in sorted(totals.items())]
        return WorkloadViewData(
            school_level=school_level,
            classes=classes,
            subjects=subjects,
            cells=cells,
        )

    def update_workload_cell(
        self, class_id: int, subject_id: int, hours: int
    ) -> None:
        if hours < 0:
            raise BadRequestError("hours must be >= 0")
        require_owned(self.db, SchoolClass, class_id, self.school_id)
        require_owned(self.db, Subject, subject_id, self.school_id)

        assignment = self.db.scalars(
            select(TeachingAssignment).where(
                TeachingAssignment.school_id == self.school_id,
                TeachingAssignment.class_id == class_id,
                TeachingAssignment.subject_id == subject_id,
                TeachingAssignment.teacher_id.is_(None),
            )
        ).first()

        if hours == 0:
            if assignment:
                self.db.delete(assignment)
                self.db.commit()
            return

        if assignment:
            assignment.hours_per_week = hours
        else:
            self.db.add(
                TeachingAssignment(
                    school_id=self.school_id,
                    class_id=class_id,
                    subject_id=subject_id,
                    hours_per_week=hours,
                    teacher_id=None,
                )
            )
        self.db.commit()
