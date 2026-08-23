"""Excel import service."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Classroom, SchoolClass, Subject, Teacher, TeachingAssignment
from app.services.session_util import resolve_session

_MAX_GROUPS = 4


def _norm_name(value: str) -> str:
    return " ".join(str(value).split()).casefold()


def _parse_hours(value) -> int:
    import pandas as pd

    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 0
    if isinstance(value, str):
        text = value.strip().replace(",", ".")
        if not text or text.lower() == "nan":
            return 0
        value = text
    try:
        hours = int(float(value))
    except (ValueError, TypeError):
        return 0
    return max(0, hours)


def _grade_and_level(class_name: str) -> tuple[int, str]:
    grade_str = "".join(ch for ch in class_name if ch.isdigit())
    grade = int(grade_str) if grade_str else 1
    level = "elementary" if grade <= 4 else "secondary"
    return grade, level


class ExcelImporter:
    """Service for importing data from Excel files"""

    def __init__(self, session: Session | None = None, school_id: int | None = None):
        self.session = resolve_session(session)
        self.school_id = school_id
        self._teachers_by_name: dict[str, Teacher] = {}
        self._classes_by_name: dict[str, SchoolClass] = {}

    def import_teachers(self, file_path):
        """
        Import teachers from Excel file.
        Expected columns: ФИО, Email, Телефон
        Returns count of imported teachers.
        """
        import pandas as pd
        df = pd.read_excel(file_path)

        # Normalize column names
        df.columns = df.columns.str.strip()

        count = 0
        for _, row in df.iterrows():
            full_name = str(row.get('ФИО', '')).strip()
            if not full_name or full_name == 'nan':
                continue

            q = self.session.query(Teacher).filter_by(full_name=full_name)
            if self.school_id is not None:
                q = q.filter_by(school_id=self.school_id)
            existing = q.first()
            if existing:
                continue

            teacher_kwargs = dict(
                full_name=full_name,
                email=str(row.get('Email', '')).strip() if pd.notna(row.get('Email')) else '',
                phone=str(row.get('Телефон', '')).strip() if pd.notna(row.get('Телефон')) else ''
            )
            if self.school_id is not None:
                teacher_kwargs['school_id'] = self.school_id
            teacher = Teacher(**teacher_kwargs)
            self.session.add(teacher)
            count += 1

        self.session.commit()
        return count

    def import_classrooms(self, file_path):
        """
        Import classrooms from Excel file.
        Expected columns: Номер, Название, Вместимость классов, Этаж, Корпус
        Returns count of imported classrooms.
        """
        import pandas as pd
        df = pd.read_excel(file_path)
        df.columns = df.columns.str.strip()

        count = 0
        for _, row in df.iterrows():
            number = str(row.get('Номер', '')).strip()
            if not number or number == 'nan':
                continue

            q = self.session.query(Classroom).filter_by(number=number)
            if self.school_id is not None:
                q = q.filter_by(school_id=self.school_id)
            existing = q.first()
            if existing:
                continue

            floor = row.get('Этаж')
            classes_cap = row.get('Вместимость классов', row.get('Вместимость', 1))
            try:
                classes_cap = int(float(classes_cap)) if pd.notna(classes_cap) else 1
            except (ValueError, TypeError):
                classes_cap = 1
            classes_cap = max(1, classes_cap)

            classroom_kwargs = dict(
                number=number,
                name=str(row.get('Название', '')).strip() if pd.notna(row.get('Название')) else '',
                floor=int(floor) if pd.notna(floor) else None,
                building=str(row.get('Корпус', '')).strip() if pd.notna(row.get('Корпус')) else '',
                classes_capacity=classes_cap
            )
            if self.school_id is not None:
                classroom_kwargs['school_id'] = self.school_id
            classroom = Classroom(**classroom_kwargs)
            self.session.add(classroom)
            count += 1

        self.session.commit()
        return count

    def import_curriculum(self, file_path, school_level):
        """
        Import curriculum (subjects x classes) from Excel.
        Rows = classes (first column)
        Columns = subjects (header row)
        Cells = hours per week (0 = not taught)
        
        Returns tuple (subjects_count, assignments_count)
        """
        import pandas as pd
        df = pd.read_excel(file_path, index_col=0)

        # Clean up
        df.index = df.index.astype(str).str.strip()
        df.columns = df.columns.str.strip()

        created_subjects = 0
        created_assignments = 0

        # Create/get subjects from columns
        subjects_map = {}
        for subject_name in df.columns:
            subject_name = str(subject_name).strip()
            if not subject_name or subject_name == 'nan':
                continue

            q = self.session.query(Subject).filter_by(name=subject_name)
            if self.school_id is not None:
                q = q.filter_by(school_id=self.school_id)
            subject = q.first()
            if not subject:
                subject_kwargs = dict(name=subject_name, color=Subject.DEFAULT_COLOR)
                if self.school_id is not None:
                    subject_kwargs['school_id'] = self.school_id
                subject = Subject(**subject_kwargs)
                self.session.add(subject)
                self.session.flush()
                created_subjects += 1
            subjects_map[subject_name] = subject

        # Create classes and assignments from rows
        for class_name in df.index:
            class_name = str(class_name).strip()
            if not class_name or class_name == 'nan':
                continue

            school_class = self._get_or_create_class(class_name, school_level)

            for subject_name in df.columns:
                subject_name = str(subject_name).strip()
                if subject_name not in subjects_map:
                    continue

                try:
                    hours = int(df.loc[class_name, subject_name])
                except (ValueError, TypeError):
                    hours = 0

                if hours == 0:
                    continue

                subject = subjects_map[subject_name]

                aq = (
                    self.session.query(TeachingAssignment)
                    .filter_by(
                        subject_id=subject.id,
                        class_id=school_class.id,
                        teacher_id=None,
                        group_number=None
                    )
                )
                if self.school_id is not None:
                    aq = aq.filter_by(school_id=self.school_id)
                existing = aq.first()

                if existing:
                    existing.hours_per_week = hours
                else:
                    assignment_kwargs = dict(
                        subject_id=subject.id,
                        class_id=school_class.id,
                        hours_per_week=hours,
                        teacher_id=None  # To be assigned later
                    )
                    if self.school_id is not None:
                        assignment_kwargs['school_id'] = self.school_id
                    assignment = TeachingAssignment(**assignment_kwargs)
                    self.session.add(assignment)
                    created_assignments += 1

        self.session.commit()
        return created_subjects, created_assignments

    def import_subject_hours(self, file_path, subject_name: str | None = None) -> dict:
        """
        Import one subject file: teachers × classes, cells = hours per week.

        Column A — teacher names. Remaining columns — classes.
        Subject name: explicit argument, otherwise the file stem.

        Inferences:
        - two (or more) teachers with hours in the same class → subgroups
        - the same teacher in several subject files → several subjects
        """
        import pandas as pd

        df = pd.read_excel(file_path)
        if df.empty or len(df.columns) < 2:
            raise ValueError(
                "В файле нужны столбец учителей и хотя бы один столбец класса"
            )

        df.columns = df.columns.astype(str).str.strip()
        teacher_col = df.columns[0]
        class_cols = [c for c in df.columns[1:] if c and c.lower() != "nan"]
        if not class_cols:
            raise ValueError("Нет столбцов с классами")

        resolved_subject = (subject_name or Path(file_path).stem).strip()
        if not resolved_subject:
            raise ValueError("Не удалось определить название предмета")

        subject, subject_created = self._get_or_create_subject(resolved_subject)

        created_teachers = 0
        created_classes = 0
        created_assignments = 0
        updated_assignments = 0
        warnings: list[str] = []
        # class_id -> [(teacher, hours), ...] in file order
        by_class: dict[int, list[tuple[Teacher, int]]] = defaultdict(list)

        for _, row in df.iterrows():
            raw_name = row.get(teacher_col)
            if raw_name is None or (isinstance(raw_name, float) and pd.isna(raw_name)):
                continue
            teacher_name = " ".join(str(raw_name).split())
            if not teacher_name or teacher_name.lower() == "nan":
                continue

            teacher, t_new = self._get_or_create_teacher(teacher_name)
            if t_new:
                created_teachers += 1

            for col in class_cols:
                hours = _parse_hours(row.get(col))
                if hours <= 0:
                    continue
                class_name = str(col).strip()
                school_class, c_new = self._get_or_create_class_inferred(class_name)
                if c_new:
                    created_classes += 1
                by_class[school_class.id].append((teacher, hours))

        subgroup_classes = 0
        for class_id, rows in by_class.items():
            seen: dict[int, TeachingAssignment] = {}
            ordered: list[TeachingAssignment] = []
            for teacher, hours in rows:
                existing = seen.get(teacher.id)
                if existing is not None:
                    existing.hours_per_week += hours
                    warnings.append(
                        f"{resolved_subject}: учитель «{teacher.full_name}» "
                        f"повторяется в одном классе — часы сложены"
                    )
                    continue
                assignment, created = self._upsert_assignment(
                    subject=subject,
                    school_class_id=class_id,
                    teacher=teacher,
                    hours=hours,
                )
                seen[teacher.id] = assignment
                ordered.append(assignment)
                if created:
                    created_assignments += 1
                else:
                    updated_assignments += 1

            n = len(ordered)
            if n >= 2:
                subgroup_classes += 1
                if n > _MAX_GROUPS:
                    warnings.append(
                        f"{resolved_subject}: в классе больше {_MAX_GROUPS} учителей "
                        f"— сохранены все, группы пронумерованы по порядку"
                    )
                for i, assignment in enumerate(ordered, start=1):
                    assignment.group_number = i
            elif n == 1:
                ordered[0].group_number = None

        self.session.commit()
        return {
            "subject": subject.name,
            "subject_created": subject_created,
            "teachers_created": created_teachers,
            "classes_created": created_classes,
            "assignments_created": created_assignments,
            "assignments_updated": updated_assignments,
            "subgroup_classes": subgroup_classes,
            "warnings": warnings,
        }

    def _school_filter(self, query, model):
        if self.school_id is not None:
            return query.filter(model.school_id == self.school_id)
        return query

    def _get_or_create_subject(self, name: str) -> tuple[Subject, bool]:
        q = self._school_filter(self.session.query(Subject).filter_by(name=name), Subject)
        subject = q.first()
        if subject:
            return subject, False
        color = self._next_subject_color()
        kwargs = dict(name=name, color=color)
        if self.school_id is not None:
            kwargs["school_id"] = self.school_id
        subject = Subject(**kwargs)
        self.session.add(subject)
        self.session.flush()
        return subject, True

    def _next_subject_color(self) -> str:
        q = self.session.query(Subject)
        if self.school_id is not None:
            q = q.filter_by(school_id=self.school_id)
        count = q.count()
        palette = Subject.COLOR_PALETTE
        return palette[count % len(palette)]

    def _get_or_create_teacher(self, full_name: str) -> tuple[Teacher, bool]:
        key = _norm_name(full_name)
        cached = self._teachers_by_name.get(key)
        if cached is not None:
            return cached, False
        q = self._school_filter(self.session.query(Teacher), Teacher)
        for teacher in q.all():
            nkey = _norm_name(teacher.full_name)
            self._teachers_by_name[nkey] = teacher
            if nkey == key:
                return teacher, False
        kwargs = dict(full_name=full_name)
        if self.school_id is not None:
            kwargs["school_id"] = self.school_id
        teacher = Teacher(**kwargs)
        self.session.add(teacher)
        self.session.flush()
        self._teachers_by_name[key] = teacher
        return teacher, True

    def _get_or_create_class_inferred(self, name: str) -> tuple[SchoolClass, bool]:
        cached = self._classes_by_name.get(name)
        if cached is not None:
            return cached, False
        q = self._school_filter(self.session.query(SchoolClass).filter_by(name=name), SchoolClass)
        school_class = q.first()
        if school_class:
            self._classes_by_name[name] = school_class
            return school_class, False
        grade, level = _grade_and_level(name)
        kwargs = dict(name=name, grade=grade, school_level=level)
        if self.school_id is not None:
            kwargs["school_id"] = self.school_id
        school_class = SchoolClass(**kwargs)
        self.session.add(school_class)
        self.session.flush()
        self._classes_by_name[name] = school_class
        return school_class, True

    def _upsert_assignment(
        self,
        *,
        subject: Subject,
        school_class_id: int,
        teacher: Teacher,
        hours: int,
    ) -> tuple[TeachingAssignment, bool]:
        q = self.session.query(TeachingAssignment).filter_by(
            subject_id=subject.id,
            class_id=school_class_id,
            teacher_id=teacher.id,
        )
        if self.school_id is not None:
            q = q.filter_by(school_id=self.school_id)
        existing = q.first()
        if existing:
            existing.hours_per_week = hours
            return existing, False
        kwargs = dict(
            subject_id=subject.id,
            class_id=school_class_id,
            teacher_id=teacher.id,
            hours_per_week=hours,
        )
        if self.school_id is not None:
            kwargs["school_id"] = self.school_id
        assignment = TeachingAssignment(**kwargs)
        self.session.add(assignment)
        self.session.flush()
        return assignment, True

    def _get_or_create_class(self, name, school_level):
        """Get or create school class by name"""
        q = self.session.query(SchoolClass).filter_by(name=name)
        if self.school_id is not None:
            q = q.filter_by(school_id=self.school_id)
        school_class = q.first()
        if not school_class:
            # Extract grade from name (e.g., "1А" -> 1, "10Б" -> 10)
            grade_str = ''.join(filter(str.isdigit, name))
            grade = int(grade_str) if grade_str else 1

            class_kwargs = dict(
                name=name,
                grade=grade,
                school_level=school_level
            )
            if self.school_id is not None:
                class_kwargs['school_id'] = self.school_id
            school_class = SchoolClass(**class_kwargs)
            self.session.add(school_class)
            self.session.flush()
        return school_class
