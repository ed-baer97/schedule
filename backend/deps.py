"""SQLAlchemy session factory for FastAPI (same DATABASE_URL as Flask)."""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app import create_app
from app.config import Config

_connect_args = (
    {"check_same_thread": False}
    if str(Config.SQLALCHEMY_DATABASE_URI).startswith("sqlite")
    else {}
)

engine = create_engine(
    Config.SQLALCHEMY_DATABASE_URI,
    connect_args=_connect_args,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


flask_app = create_app()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
