"""SQLAlchemy session factory for FastAPI."""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

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


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
