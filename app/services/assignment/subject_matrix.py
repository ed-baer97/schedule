"""Subject × class assignment matrix."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.models import SchoolClass, Subject, Teacher, TeachingAssignment
from app.services.assignment.types import (
    SubjectAssignClassData,
    SubjectAssignmentsSaveResultData,
    SubjectAssignmentsViewData,
)
from app.services.dto import subject_data, teacher_brief
from app.services.errors import NotFoundError
from app.services.tenancy import require_owned


class AssignmentSubjectMatrixMixin:
    def get_subject_assignments(
        self, subject_id: int, school_level: str
    ) -> SubjectAssignmentsViewData:
        subject = self.db.execute(
            select(Subject)
            .options(joinedload(Subject.classrooms))
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
            subject=subject_data(subject),
            school_level=school_level,
            classes=class_rows,
            attached_teachers=[teacher_brief(t) for t in attached_teachers],
            all_teachers=[teacher_brief(t) for t in all_teachers],
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
                    self.create(
                        subject_id=subject.id,
                        class_id=school_class.id,
                        hours_per_week=hours,
                        teacher_id=checked_teachers[1],
                        group_number=2,
                        commit=False,
                    )

        if errors:
            self.db.rollback()
            return SubjectAssignmentsSaveResultData(ok=False, errors=errors)
        self.db.commit()
        return SubjectAssignmentsSaveResultData(ok=True, errors=[])

