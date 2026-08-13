"""Dashboard stats schema."""
from pydantic import BaseModel


class DashboardStatsOut(BaseModel):
    teachers_count: int
    classes_count: int
    subjects_count: int
    classrooms_count: int
    elementary_classes: int
    secondary_classes: int
    elementary_assignments: int
    secondary_assignments: int
    elementary_scheduled: int
    secondary_scheduled: int
