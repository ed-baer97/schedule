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
        # Accept postgresql:// and normalize to psycopg3 driver when needed.
        if url.startswith("postgresql://") and "+psycopg" not in url:
            return "postgresql+psycopg://" + url[len("postgresql://") :]
        if url.startswith("postgres://"):
            return "postgresql+psycopg://" + url[len("postgres://") :]
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


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


class Config:
    SQLALCHEMY_DATABASE_URI = _normalize_database_uri(os.environ.get("DATABASE_URL"))
    UPLOAD_FOLDER = str(PROJECT_ROOT / "uploads")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-secret-change-me"
    COOKIE_SECURE = _env_bool("COOKIE_SECURE", default=False)
    COOKIE_NAME = os.environ.get("COOKIE_NAME") or "schedule_session"
    JWT_EXPIRE_HOURS = int(os.environ.get("JWT_EXPIRE_HOURS") or "168")
    BOOTSTRAP_ADMIN_EMAIL = (os.environ.get("BOOTSTRAP_ADMIN_EMAIL") or "").strip()
    BOOTSTRAP_ADMIN_PASSWORD = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD") or ""
    REDIS_URL = os.environ.get("REDIS_URL") or "redis://localhost:6379/0"
    CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL") or REDIS_URL
    CELERY_RESULT_BACKEND = (
        os.environ.get("CELERY_RESULT_BACKEND") or "redis://localhost:6379/1"
    )
    SOLVER_TIME_LIMIT_SEC = int(os.environ.get("SOLVER_TIME_LIMIT_SEC") or "90")
