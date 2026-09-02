"""Schedule cell write commands."""
from __future__ import annotations

from sqlalchemy import select

from app.models import Classroom, ScheduleCell, SchoolClass, TeachingAssignment
from app.services.errors import ValidationConflict
from app.services.schedule.types import Placement
from app.services.schedule_mapping import cell_to_schedule_dict, reload_cell
from app.services.tenancy import require_owned


class ScheduleCommandsMixin:
    def insert_cell(
        self,
        *,
        class_id: int,
        day_of_week: int,
        lesson_number: int,
        assignment_id: int,
        classroom_id: int | None = None,
        validate: bool = False,
        commit: bool = False,
    ) -> ScheduleCell:
        """Single write-path for ScheduleCell (manual grid, auto, solver)."""
        cell = ScheduleCell(
            school_id=self.school_id,
            class_id=class_id,
            day_of_week=day_of_week,
            lesson_number=lesson_number,
            assignment_id=assignment_id,
            classroom_id=classroom_id,
        )
        if validate:
            assignment = require_owned(
                self.db, TeachingAssignment, assignment_id, self.school_id
            )
            require_owned(self.db, SchoolClass, class_id, self.school_id)
            if classroom_id is not None:
                require_owned(self.db, Classroom, classroom_id, self.school_id)
            _ = assignment.school_class, assignment.teacher, assignment.subject
            errors = self.validator.validate_cell(
                assignment=assignment,
                day=day_of_week,
                lesson=lesson_number,
                classroom_id=classroom_id,
            )
            if errors:
                raise ValidationConflict(errors)
        self.db.add(cell)
        if commit:
            self.db.commit()
        else:
            self.db.flush()
        return cell

    def apply_placements(
        self,
        placements: list[Placement],
        *,
        validate: bool = False,
        commit: bool = True,
    ) -> int:
        """Insert many cells via insert_cell; one commit for the batch."""
        count = 0
        for p in placements:
            self.insert_cell(
                class_id=p.class_id,
                day_of_week=p.day_of_week,
                lesson_number=p.lesson_number,
                assignment_id=p.assignment_id,
                classroom_id=p.classroom_id,
                validate=validate,
                commit=False,
            )
            count += 1
        if commit:
            self.db.commit()
        else:
            self.db.flush()
        return count

    def create_cell(
        self,
        *,
        class_id: int,
        day_of_week: int,
        lesson_number: int,
        assignment_id: int,
        classroom_id: int | None,
    ) -> dict:
        assignment = require_owned(
            self.db, TeachingAssignment, assignment_id, self.school_id
        )
        if assignment.class_id != class_id:
            raise ValidationConflict(["Этот предмет назначен другому классу"])
        cell = self.insert_cell(
            class_id=class_id,
            day_of_week=day_of_week,
            lesson_number=lesson_number,
            assignment_id=assignment_id,
            classroom_id=classroom_id,
            validate=True,
            commit=True,
        )
        return cell_to_schedule_dict(reload_cell(self.db, cell.id))

    def _apply_move(
        self,
        cell_id: int,
        *,
        day_of_week: int,
        lesson_number: int,
        class_id: int | None = None,
        classroom_id: int | None = None,
        set_classroom: bool = False,
        validate: bool = True,
        commit: bool = True,
        allow_class_change: bool = True,
    ) -> ScheduleCell:
        """Shared move/reposition path for ScheduleCell."""
        cell = require_owned(self.db, ScheduleCell, cell_id, self.school_id)

        new_class_id = cell.class_id
        validation_assignment = cell.assignment
        if allow_class_change and class_id is not None:
            require_owned(self.db, SchoolClass, class_id, self.school_id)
            new_class_id = class_id
            assignment = cell.assignment
            if new_class_id != assignment.class_id:
                assignment_for_target = self.db.scalars(
                    select(TeachingAssignment).where(
                        TeachingAssignment.class_id == new_class_id,
                        TeachingAssignment.subject_id == assignment.subject_id,
                        TeachingAssignment.teacher_id == assignment.teacher_id,
                        TeachingAssignment.group_number == assignment.group_number,
                        TeachingAssignment.school_id == self.school_id,
                    )
                ).first()
                if assignment_for_target is None:
                    raise ValidationConflict(
                        [
                            "У целевого класса нет такого назначения (предмет/учитель/группа)."
                        ]
                    )
                validation_assignment = assignment_for_target

        new_classroom_id = cell.classroom_id
        if set_classroom:
            new_classroom_id = classroom_id
            if new_classroom_id is not None:
                require_owned(self.db, Classroom, new_classroom_id, self.school_id)

        if validate:
            _ = (
                validation_assignment.school_class,
                validation_assignment.teacher,
                validation_assignment.subject,
            )
            errors = self.validator.validate_cell(
                assignment=validation_assignment,
                day=day_of_week,
                lesson=lesson_number,
                classroom_id=new_classroom_id,
                exclude_cell_id=cell_id,
            )
            if errors:
                raise ValidationConflict(errors)

        cell.day_of_week = day_of_week
        cell.lesson_number = lesson_number
        if allow_class_change and class_id is not None and new_class_id != cell.class_id:
            cell.class_id = new_class_id
            cell.assignment_id = validation_assignment.id
        if set_classroom:
            cell.classroom_id = new_classroom_id
        if commit:
            self.db.commit()
        else:
            self.db.flush()
        return cell

    def move_cell(
        self,
        cell_id: int,
        *,
        day_of_week: int,
        lesson_number: int,
        class_id: int | None = None,
        classroom_id: int | None = None,
        set_classroom: bool = False,
    ) -> dict:
        cell = self._apply_move(
            cell_id,
            day_of_week=day_of_week,
            lesson_number=lesson_number,
            class_id=class_id,
            classroom_id=classroom_id,
            set_classroom=set_classroom,
            validate=True,
            commit=True,
            allow_class_change=True,
        )
        return cell_to_schedule_dict(reload_cell(self.db, cell.id))

    def swap_classrooms(self, cell_id: int, other_cell_id: int) -> dict:
        """Exchange classroom_id between two cells, then validate both."""
        if cell_id == other_cell_id:
            raise ValidationConflict(["Нельзя поменять ячейку саму с собой"])
        cell = require_owned(self.db, ScheduleCell, cell_id, self.school_id)
        other = require_owned(self.db, ScheduleCell, other_cell_id, self.school_id)
        if other.classroom_id is None:
            raise ValidationConflict(["У второго урока нет кабинета для обмена"])

        cell_assignment = cell.assignment
        other_assignment = other.assignment
        _ = (
            cell_assignment.school_class,
            cell_assignment.teacher,
            cell_assignment.subject,
        )
        _ = (
            other_assignment.school_class,
            other_assignment.teacher,
            other_assignment.subject,
        )

        cell.classroom_id, other.classroom_id = other.classroom_id, cell.classroom_id
        self.db.flush()

        errors: list[str] = []
        errors.extend(
            self.validator.validate_cell(
                assignment=cell_assignment,
                day=cell.day_of_week,
                lesson=cell.lesson_number,
                classroom_id=cell.classroom_id,
                exclude_cell_id=cell.id,
            )
        )
        errors.extend(
            self.validator.validate_cell(
                assignment=other_assignment,
                day=other.day_of_week,
                lesson=other.lesson_number,
                classroom_id=other.classroom_id,
                exclude_cell_id=other.id,
            )
        )
        if errors:
            self.db.rollback()
            raise ValidationConflict(errors)
        self.db.commit()
        return {
            "cell": cell_to_schedule_dict(reload_cell(self.db, cell.id)),
            "other": cell_to_schedule_dict(reload_cell(self.db, other.id)),
        }

    def delete_cell(self, cell_id: int) -> None:
        cell = require_owned(self.db, ScheduleCell, cell_id, self.school_id)
        self.db.delete(cell)
        self.db.commit()

    def reposition_cell(
        self,
        cell_id: int,
        *,
        day_of_week: int,
        lesson_number: int,
        classroom_id: int | None = None,
        set_classroom: bool = False,
        validate: bool = False,
        commit: bool = False,
    ) -> ScheduleCell:
        """Move a cell to another slot (solver/auto path; no commit by default)."""
        return self._apply_move(
            cell_id,
            day_of_week=day_of_week,
            lesson_number=lesson_number,
            classroom_id=classroom_id,
            set_classroom=set_classroom,
            validate=validate,
            commit=commit,
            allow_class_change=False,
        )
    def delete_cells(
        self,
        *,
        class_ids: list[int] | None = None,
        cell_ids: list[int] | None = None,
        teacher_id: int | None = None,
        school_level: str | None = None,
        class_id: int | None = None,
        days_of_week: list[int] | None = None,
        commit: bool = False,
    ) -> int:
        """Batch-delete ScheduleCell rows scoped to this school."""
        stmt = select(ScheduleCell).where(ScheduleCell.school_id == self.school_id)
        if cell_ids is not None:
            if not cell_ids:
                return 0
            stmt = stmt.where(ScheduleCell.id.in_(cell_ids))
        if class_ids is not None:
            if not class_ids:
                return 0
            stmt = stmt.where(ScheduleCell.class_id.in_(class_ids))
        if days_of_week is not None:
            if not days_of_week:
                return 0
            stmt = stmt.where(ScheduleCell.day_of_week.in_(days_of_week))
        if class_id is not None:
            stmt = stmt.where(ScheduleCell.class_id == class_id)
        elif school_level is not None:
            stmt = stmt.join(SchoolClass).where(
                SchoolClass.school_level == school_level,
                SchoolClass.school_id == self.school_id,
            )
        if teacher_id is not None:
            stmt = stmt.join(
                TeachingAssignment,
                TeachingAssignment.id == ScheduleCell.assignment_id,
            ).where(TeachingAssignment.teacher_id == teacher_id)

        cells = list(self.db.scalars(stmt).unique().all())
        count = len(cells)
        for cell in cells:
            self.db.delete(cell)
        if count:
            if commit:
                self.db.commit()
            else:
                self.db.flush()
        return count


