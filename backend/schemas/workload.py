"""Workload API schemas."""
from pydantic import BaseModel, ConfigDict


class SchoolClassBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    grade: int


class SubjectBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


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
