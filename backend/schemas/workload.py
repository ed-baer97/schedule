"""Workload API schemas."""
from pydantic import BaseModel

from backend.schemas.common import SchoolClassBrief, SubjectBrief

__all__ = [
    "SchoolClassBrief",
    "SubjectBrief",
    "WorkloadCellOut",
    "WorkloadOut",
    "WorkloadCellUpdate",
]


class WorkloadCellOut(BaseModel):
    class_id: int
    subject_id: int
    hours: int


class WorkloadOut(BaseModel):
    school_level: str
    classes: list[SchoolClassBrief]
    subjects: list[SubjectBrief]
    cells: list[WorkloadCellOut]


class WorkloadCellUpdate(BaseModel):
    class_id: int
    subject_id: int
    hours: int
