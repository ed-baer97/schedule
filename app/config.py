"""Application configuration."""
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")


def _normalize_database_uri(raw: str | None) -> str:
    """Resolve SQLite paths against the repo root, independent of cwd."""
    url = (raw or "").strip() or "sqlite:///instance/school_schedule.db"
    if not url.startswith("sqlite"):
        return url
    if url.startswith("sqlite:///:memory:") or url == "sqlite://":
        return url
    prefix = "sqlite:///"
    if url.startswith("sqlite:////"):
        return url
    path_part = url[len(prefix) :] if url.startswith(prefix) else url
    if not path_part or path_part == ":memory:":
        return url
    p = Path(path_part)
    if not p.is_absolute():
        p = (PROJECT_ROOT / p).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    return "sqlite:///" + p.as_posix()


class Config:
    SQLALCHEMY_DATABASE_URI = _normalize_database_uri(os.environ.get("DATABASE_URL"))
    UPLOAD_FOLDER = str(PROJECT_ROOT / "uploads")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
