"""Reports API schemas."""
from pydantic import BaseModel


class ReportCellOut(BaseModel):
    id: int
    day_of_week: int
    lesson_number: int
    subject_name: str
    subject_color: str
    teacher_name: str | None = None
    class_name: str
    classroom_name: str | None = None
    group_number: int | None = None


class ClassReportOut(BaseModel):
    class_id: int
    class_name: str
    school_level: str
    day_names: list[str]
    working_days: int
    max_lessons: int
    lessons_range: list[int]
    class_hour_day: int | None = None
    class_hour_time_label: str | None = None
    lesson_times_by_day: dict[int, dict[int, str]]
    cells: list[ReportCellOut]


class TeacherReportOut(BaseModel):
    teacher_id: int
    teacher_name: str
    day_names: list[str]
    working_days: int
    max_lessons: int
    cells: list[ReportCellOut]
