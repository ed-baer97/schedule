"""AssignmentService composed from mixins."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.assignment.crud import AssignmentCrudMixin
from app.services.assignment.subject_matrix import AssignmentSubjectMatrixMixin
from app.services.assignment.workload import AssignmentWorkloadMixin


class AssignmentService(
    AssignmentCrudMixin,
    AssignmentSubjectMatrixMixin,
    AssignmentWorkloadMixin,
):
    def __init__(self, db: Session, school_id: int):
        self.db = db
        self.school_id = school_id
