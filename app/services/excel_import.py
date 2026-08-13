"""
Excel import service
"""
from sqlalchemy.orm import Session

from app.models import Teacher, Subject, SchoolClass, TeachingAssignment, Classroom
from app.services.session_util import resolve_session


class ExcelImporter:
    """Service for importing data from Excel files"""

    def __init__(self, session: Session | None = None):
        self.session = resolve_session(session)

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

            existing = self.session.query(Teacher).filter_by(full_name=full_name).first()
            if existing:
                continue

            teacher = Teacher(
                full_name=full_name,
                email=str(row.get('Email', '')).strip() if pd.notna(row.get('Email')) else '',
                phone=str(row.get('Телефон', '')).strip() if pd.notna(row.get('Телефон')) else ''
            )
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

            existing = self.session.query(Classroom).filter_by(number=number).first()
            if existing:
                continue

            floor = row.get('Этаж')
            classes_cap = row.get('Вместимость классов', row.get('Вместимость', 1))
            try:
                classes_cap = int(float(classes_cap)) if pd.notna(classes_cap) else 1
            except (ValueError, TypeError):
                classes_cap = 1
            classes_cap = max(1, classes_cap)

            classroom = Classroom(
                number=number,
                name=str(row.get('Название', '')).strip() if pd.notna(row.get('Название')) else '',
                floor=int(floor) if pd.notna(floor) else None,
                building=str(row.get('Корпус', '')).strip() if pd.notna(row.get('Корпус')) else '',
                classes_capacity=classes_cap
            )
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

            subject = self.session.query(Subject).filter_by(name=subject_name).first()
            if not subject:
                subject = Subject(name=subject_name, color=Subject.DEFAULT_COLOR)
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

                existing = (
                    self.session.query(TeachingAssignment)
                    .filter_by(
                        subject_id=subject.id,
                        class_id=school_class.id,
                        teacher_id=None,
                        group_number=None
                    )
                    .first()
                )

                if existing:
                    existing.hours_per_week = hours
                else:
                    assignment = TeachingAssignment(
                        subject_id=subject.id,
                        class_id=school_class.id,
                        hours_per_week=hours,
                        teacher_id=None  # To be assigned later
                    )
                    self.session.add(assignment)
                    created_assignments += 1

        self.session.commit()
        return created_subjects, created_assignments

    def _get_or_create_class(self, name, school_level):
        """Get or create school class by name"""
        school_class = self.session.query(SchoolClass).filter_by(name=name).first()
        if not school_class:
            # Extract grade from name (e.g., "1А" -> 1, "10Б" -> 10)
            grade_str = ''.join(filter(str.isdigit, name))
            grade = int(grade_str) if grade_str else 1

            school_class = SchoolClass(
                name=name,
                grade=grade,
                school_level=school_level
            )
            self.session.add(school_class)
            self.session.flush()
        return school_class
