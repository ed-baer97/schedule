"""SQLAlchemy session factory and auth/tenant dependencies for FastAPI."""
from collections.abc import Generator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import Config
from app.models import School, User
from app.models.user import ROLE_PLATFORM_ADMIN
from backend.security import decode_access_token

_IS_SQLITE = str(Config.SQLALCHEMY_DATABASE_URI).startswith("sqlite")
_connect_args = (
    {"check_same_thread": False, "timeout": 30}
    if _IS_SQLITE
    else {}
)

engine = create_engine(
    Config.SQLALCHEMY_DATABASE_URI,
    connect_args=_connect_args,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


if _IS_SQLITE:
    @event.listens_for(engine, "connect")
    def _sqlite_on_connect(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    request: Request, db: Session = Depends(get_db)
) -> User:
    token = request.cookies.get(Config.COOKIE_NAME)
    if not token:
        auth = request.headers.get("Authorization") or ""
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется вход",
        )
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Сессия недействительна",
        ) from exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не найден или отключён",
        )
    return user


def get_current_school(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> School:
    """School-scoped routes: platform_admin without school_id cannot access."""
    if user.school_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет привязки к школе. Используйте раздел админки платформы.",
        )
    school = db.get(School, user.school_id)
    if school is None or not school.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Школа не найдена или отключена",
        )
    return school


def require_platform_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != ROLE_PLATFORM_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Только администратор платформы",
        )
    return user
