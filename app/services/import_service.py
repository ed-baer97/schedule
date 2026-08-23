"""Excel import orchestration (file validation + ExcelImporter)."""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import Config
from app.services.errors import BadRequestError, NotFoundError
from app.services.excel_import import ExcelImporter

_ALLOWED_EXTENSIONS = {"xlsx", "xls"}
_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "excel_templates"
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


@dataclass
class ImportTeachersResultData:
    count: int
    message: str


@dataclass
class ImportClassroomsResultData:
    count: int
    message: str


@dataclass
class ImportCurriculumResultData:
    subjects_count: int
    assignments_count: int
    message: str


@dataclass
class SubjectHoursFileResultData:
    subject: str
    subject_created: bool
    teachers_created: int
    classes_created: int
    assignments_created: int
    assignments_updated: int
    subgroup_classes: int
    warnings: list[str] = field(default_factory=list)


@dataclass
class ImportSubjectHoursResultData:
    files: list[SubjectHoursFileResultData]
    message: str


@dataclass
class TemplateFileData:
    path: Path
    download_name: str


def _allowed(filename: str | None) -> bool:
    if not filename or "." not in filename:
        return False
    return filename.rsplit(".", 1)[1].lower() in _ALLOWED_EXTENSIONS


class ImportService:
    def __init__(self, db: Session, school_id: int):
        self.db = db
        self.school_id = school_id
        self._importer = ExcelImporter(db, school_id=school_id)

    def save_upload(self, *, filename: str | None, content: bytes) -> str:
        if not filename:
            raise BadRequestError("Файл не выбран")
        if not _allowed(filename):
            raise BadRequestError("Неверный формат. Используйте .xlsx или .xls")
        upload_folder = Path(Config.UPLOAD_FOLDER)
        upload_folder.mkdir(parents=True, exist_ok=True)
        suffix = "." + filename.rsplit(".", 1)[1].lower()
        fd, path = tempfile.mkstemp(suffix=suffix, dir=str(upload_folder))
        os.close(fd)
        with open(path, "wb") as fh:
            fh.write(content)
        return path

    @staticmethod
    def cleanup(path: str) -> None:
        try:
            os.remove(path)
        except OSError:
            pass

    def import_teachers(self, path: str) -> ImportTeachersResultData:
        try:
            count = self._importer.import_teachers(path)
        except Exception as exc:  # noqa: BLE001
            raise BadRequestError(f"Ошибка импорта: {exc}") from exc
        return ImportTeachersResultData(
            count=count, message=f"Импортировано учителей: {count}"
        )

    def import_classrooms(self, path: str) -> ImportClassroomsResultData:
        try:
            count = self._importer.import_classrooms(path)
        except Exception as exc:  # noqa: BLE001
            raise BadRequestError(f"Ошибка импорта: {exc}") from exc
        return ImportClassroomsResultData(
            count=count, message=f"Импортировано кабинетов: {count}"
        )

    def import_curriculum(
        self, path: str, school_level: str
    ) -> ImportCurriculumResultData:
        if school_level not in ("elementary", "secondary"):
            raise BadRequestError("Неверный уровень школы")
        try:
            subjects_count, assignments_count = self._importer.import_curriculum(
                path, school_level
            )
        except Exception as exc:  # noqa: BLE001
            raise BadRequestError(f"Ошибка импорта: {exc}") from exc
        return ImportCurriculumResultData(
            subjects_count=subjects_count,
            assignments_count=assignments_count,
            message=(
                f"Импортировано предметов: {subjects_count}, "
                f"записей нагрузки: {assignments_count}"
            ),
        )

    def import_subject_hours(
        self,
        *,
        files: list[tuple[str | None, bytes]],
        subject: str | None = None,
    ) -> ImportSubjectHoursResultData:
        if not files:
            raise BadRequestError("Файлы не выбраны")
        subject_name = (subject or "").strip() or None
        if len(files) > 1 and subject_name:
            raise BadRequestError(
                "Название предмета задаётся только при загрузке одного файла; "
                "для нескольких файлов имя берётся из имени файла"
            )

        results: list[SubjectHoursFileResultData] = []
        saved_paths: list[str] = []
        try:
            for filename, content in files:
                path = self.save_upload(filename=filename, content=content)
                saved_paths.append(path)
                stem = Path(filename or path).stem
                name = subject_name if len(files) == 1 else None
                try:
                    payload = self._importer.import_subject_hours(
                        path, subject_name=name or stem
                    )
                except ValueError as exc:
                    raise BadRequestError(str(exc)) from exc
                except Exception as exc:  # noqa: BLE001
                    raise BadRequestError(
                        f"Ошибка импорта «{stem}»: {exc}"
                    ) from exc
                results.append(SubjectHoursFileResultData(**payload))
        finally:
            for path in saved_paths:
                self.cleanup(path)

        subjects = ", ".join(item.subject for item in results)
        created = sum(item.assignments_created for item in results)
        updated = sum(item.assignments_updated for item in results)
        subgroups = sum(item.subgroup_classes for item in results)
        return ImportSubjectHoursResultData(
            files=results,
            message=(
                f"Предметы: {subjects}. "
                f"Назначений создано: {created}, обновлено: {updated}"
                + (f", классов с подгруппами: {subgroups}" if subgroups else "")
            ),
        )

    @staticmethod
    def resolve_template(template_type: str) -> TemplateFileData:
        if template_type not in _TEMPLATE_NAMES:
            raise NotFoundError("Неверный тип шаблона")
        fname, download_name = _TEMPLATE_NAMES[template_type]
        path = _TEMPLATES_DIR / fname
        if not path.exists():
            raise NotFoundError("Шаблон не найден")
        return TemplateFileData(path=path, download_name=download_name)
