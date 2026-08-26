"""Database models"""
from app.models.classroom import Classroom, classroom_subjects
from app.models.job import Job
from app.models.schedule_cell import ScheduleCell
from app.models.schedule_settings import ScheduleSettings
from app.models.school import School
from app.models.school_class import SchoolClass
from app.models.shift import Shift
from app.models.shift_lesson_time import ShiftLessonTime
from app.models.subject import Subject
from app.models.teacher import Teacher
from app.models.teaching_assignment import TeachingAssignment
from app.models.user import InviteToken, User

__all__ = [
    "School",
    "User",
    "InviteToken",
    "Job",
    "Teacher",
    "Classroom",
    "classroom_subjects",
    "Shift",
    "ShiftLessonTime",
    "SchoolClass",
    "Subject",
    "TeachingAssignment",
    "ScheduleCell",
    "ScheduleSettings",
]
