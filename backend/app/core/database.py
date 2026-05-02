"""Database engine and session management."""
from __future__ import annotations

from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


def _ensure_sqlite_path(url: str) -> str:
    """Ensure parent directory of sqlite db exists."""
    if url.startswith("sqlite:///"):
        path = url.replace("sqlite:///", "", 1)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    return url


_engine_url = _ensure_sqlite_path(settings.database_url)

connect_args = {}
if _engine_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(_engine_url, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables. Imports models so they register."""
    from app import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
