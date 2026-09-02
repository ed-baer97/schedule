"""Excel import & template downloads."""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models import School
from app.services.import_service import ImportService
from backend.deps import get_current_school, get_db

router = APIRouter()


class ImportTeachersResult(BaseModel):
    count: int
    message: str


class ImportClassroomsResult(BaseModel):
    count: int
    message: str


class ImportCurriculumResult(BaseModel):
    subjects_count: int
    assignments_count: int
    message: str


class SubjectHoursFileResult(BaseModel):
    subject: str
    subject_created: bool
    teachers_created: int
    classes_created: int
    assignments_created: int
    assignments_updated: int
    subgroup_classes: int
    warnings: list[str] = Field(default_factory=list)


class ImportSubjectHoursResult(BaseModel):
    files: list[SubjectHoursFileResult]
    message: str


class ImportScheduleResult(BaseModel):
    placed: int
    skipped_existing: int
    unmatched: int
    cleared: int
    warnings: list[str] = Field(default_factory=list)
    message: str


@router.post(
    "/teachers",
    response_model=ImportTeachersResult,
)
def import_teachers(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> ImportTeachersResult:
    svc = ImportService(db, school.id)
    path = svc.save_upload(filename=file.filename, content=file.file.read())
    try:
        result = svc.import_teachers(path)
    finally:
        svc.cleanup(path)
    return ImportTeachersResult(count=result.count, message=result.message)


@router.post(
    "/classrooms",
    response_model=ImportClassroomsResult,
)
def import_classrooms(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> ImportClassroomsResult:
    svc = ImportService(db, school.id)
    path = svc.save_upload(filename=file.filename, content=file.file.read())
    try:
        result = svc.import_classrooms(path)
    finally:
        svc.cleanup(path)
    return ImportClassroomsResult(count=result.count, message=result.message)


@router.post(
    "/curriculum/{school_level}",
    response_model=ImportCurriculumResult,
)
def import_curriculum(
    school_level: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> ImportCurriculumResult:
    svc = ImportService(db, school.id)
    path = svc.save_upload(filename=file.filename, content=file.file.read())
    try:
        result = svc.import_curriculum(path, school_level)
    finally:
        svc.cleanup(path)
    return ImportCurriculumResult(
        subjects_count=result.subjects_count,
        assignments_count=result.assignments_count,
        message=result.message,
    )


@router.post("/schedule", response_model=ImportScheduleResult)
def import_schedule(
    file: UploadFile = File(...),
    replace: bool = Form(False),
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> ImportScheduleResult:
    svc = ImportService(db, school.id)
    path = svc.save_upload(filename=file.filename, content=file.file.read())
    try:
        result = svc.import_schedule(path, replace=replace)
    finally:
        svc.cleanup(path)
    return ImportScheduleResult(
        placed=result.placed,
        skipped_existing=result.skipped_existing,
        unmatched=result.unmatched,
        cleared=result.cleared,
        warnings=result.warnings,
        message=result.message,
    )


@router.post("/subject-hours", response_model=ImportSubjectHoursResult)
def import_subject_hours(
    files: list[UploadFile] = File(...),
    subject: str | None = Form(None),
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> ImportSubjectHoursResult:
    svc = ImportService(db, school.id)
    payloads = [(f.filename, f.file.read()) for f in files]
    result = svc.import_subject_hours(files=payloads, subject=subject)
    return ImportSubjectHoursResult(
        files=[
            SubjectHoursFileResult(
                subject=item.subject,
                subject_created=item.subject_created,
                teachers_created=item.teachers_created,
                classes_created=item.classes_created,
                assignments_created=item.assignments_created,
                assignments_updated=item.assignments_updated,
                subgroup_classes=item.subgroup_classes,
                warnings=item.warnings,
            )
            for item in result.files
        ],
        message=result.message,
    )


@router.get("/template/{template_type}")
def download_template(template_type: str) -> FileResponse:
    tpl = ImportService.resolve_template(template_type)
    safe = quote(tpl.download_name)
    return FileResponse(
        str(tpl.path),
        filename=tpl.download_name,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{safe}",
        },
    )
