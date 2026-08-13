"""Excel import & template downloads."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import Config
from app.services.excel_import import ExcelImporter
from backend.deps import get_db

router = APIRouter()

_ALLOWED_EXTENSIONS = {"xlsx", "xls"}
_TEMPLATES_DIR = (
    Path(__file__).resolve().parents[2] / "app" / "excel_templates"
)
_TEMPLATE_NAMES = {
    "teachers": ("teachers_template.xlsx", "шаблон_учителя.xlsx"),
    "classrooms": ("classrooms_template.xlsx", "шаблон_кабинеты.xlsx"),
    "curriculum_elementary": (
        "curriculum_elementary_template.xlsx",
        "шаблон_учебный_план_начальная.xlsx",
    ),
    "curriculum_secondary": (
        "curriculum_secondary_template.xlsx",
        "шаблон_учебный_план_основная.xlsx",
    ),
}


def _allowed(filename: str | None) -> bool:
    if not filename or "." not in filename:
        return False
    return filename.rsplit(".", 1)[1].lower() in _ALLOWED_EXTENSIONS


def _save_upload(file: UploadFile) -> str:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Файл не выбран")
    if not _allowed(file.filename):
        raise HTTPException(
            status_code=400, detail="Неверный формат. Используйте .xlsx или .xls"
        )
    upload_folder = Path(Config.UPLOAD_FOLDER)
    upload_folder.mkdir(parents=True, exist_ok=True)
    suffix = "." + file.filename.rsplit(".", 1)[1].lower()
    fd, path = tempfile.mkstemp(suffix=suffix, dir=str(upload_folder))
    os.close(fd)
    with open(path, "wb") as fh:
        fh.write(file.file.read())
    return path


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


@router.post(
    "/teachers",
    response_model=ImportTeachersResult,
)
def import_teachers(
    file: UploadFile = File(...), db: Session = Depends(get_db)
) -> ImportTeachersResult:
    path = _save_upload(file)
    try:
        count = ExcelImporter(db).import_teachers(path)
    except Exception as exc:  # noqa: BLE001 — surface to API caller
        raise HTTPException(status_code=400, detail=f"Ошибка импорта: {exc}") from exc
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    return ImportTeachersResult(count=count, message=f"Импортировано учителей: {count}")


@router.post(
    "/classrooms",
    response_model=ImportClassroomsResult,
)
def import_classrooms(
    file: UploadFile = File(...), db: Session = Depends(get_db)
) -> ImportClassroomsResult:
    path = _save_upload(file)
    try:
        count = ExcelImporter(db).import_classrooms(path)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Ошибка импорта: {exc}") from exc
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    return ImportClassroomsResult(count=count, message=f"Импортировано кабинетов: {count}")


@router.post(
    "/curriculum/{school_level}",
    response_model=ImportCurriculumResult,
)
def import_curriculum(
    school_level: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> ImportCurriculumResult:
    if school_level not in ("elementary", "secondary"):
        raise HTTPException(status_code=400, detail="Неверный уровень школы")
    path = _save_upload(file)
    try:
        subjects_count, assignments_count = ExcelImporter(db).import_curriculum(
            path, school_level
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Ошибка импорта: {exc}") from exc
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    return ImportCurriculumResult(
        subjects_count=subjects_count,
        assignments_count=assignments_count,
        message=(
            f"Импортировано предметов: {subjects_count}, "
            f"записей нагрузки: {assignments_count}"
        ),
    )


@router.get("/template/{template_type}")
def download_template(template_type: str) -> FileResponse:
    if template_type not in _TEMPLATE_NAMES:
        raise HTTPException(status_code=404, detail="Неверный тип шаблона")
    fname, download_name = _TEMPLATE_NAMES[template_type]
    path = _TEMPLATES_DIR / fname
    if not path.exists():
        raise HTTPException(status_code=404, detail="Шаблон не найден")
    safe = quote(download_name)
    return FileResponse(
        str(path),
        filename=download_name,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{safe}",
        },
    )
