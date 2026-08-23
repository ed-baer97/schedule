"""Reports & Excel exports."""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.models import School
from app.services.errors import ServiceError
from app.services.report_service import ReportService
from backend.deps import get_current_school, get_db
from backend.http_errors import raise_http
from backend.schemas.reports import ClassReportOut, ReportCellOut, TeacherReportOut

router = APIRouter()

_XLSX_MIME = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


def _xlsx_stream(buf, filename: str) -> StreamingResponse:
    buf.seek(0)
    safe = quote(filename)
    return StreamingResponse(
        buf,
        media_type=_XLSX_MIME,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{safe}",
        },
    )


@router.get("/class/{class_id}", response_model=ClassReportOut)
def class_report(
    class_id: int,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> ClassReportOut:
    try:
        data = ReportService(db, school.id).class_report(class_id)
        cells = [ReportCellOut(**c) for c in data.pop("cells")]
        return ClassReportOut(**data, cells=cells)
    except ServiceError as exc:
        raise_http(exc)


@router.get("/teacher/{teacher_id}", response_model=TeacherReportOut)
def teacher_report(
    teacher_id: int,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> TeacherReportOut:
    try:
        data = ReportService(db, school.id).teacher_report(teacher_id)
        cells = [ReportCellOut(**c) for c in data.pop("cells")]
        return TeacherReportOut(**data, cells=cells)
    except ServiceError as exc:
        raise_http(exc)


@router.get("/export/class/{class_id}")
def export_class(
    class_id: int,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> StreamingResponse:
    try:
        export = ReportService(db, school.id).export_class(class_id)
        return _xlsx_stream(export.buffer, export.filename)
    except ServiceError as exc:
        raise_http(exc)


@router.get("/export/teacher/{teacher_id}")
def export_teacher(
    teacher_id: int,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> StreamingResponse:
    try:
        export = ReportService(db, school.id).export_teacher(teacher_id)
        return _xlsx_stream(export.buffer, export.filename)
    except ServiceError as exc:
        raise_http(exc)


@router.get("/export/all/{school_level}")
def export_all(
    school_level: str,
    db: Session = Depends(get_db),
    school: School = Depends(get_current_school),
) -> StreamingResponse:
    try:
        export = ReportService(db, school.id).export_all(school_level)
        return _xlsx_stream(export.buffer, export.filename)
    except ServiceError as exc:
        raise_http(exc)
