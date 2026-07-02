"""Database engine, session factory, and declarative base."""
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from ..config import settings


class Base(DeclarativeBase):
    pass


# Engine is created only when a DATABASE_URL is configured. In stub mode this
# stays None and the app uses the in-memory store instead.
engine = (
    create_engine(settings.database_url, pool_pre_ping=True, future=True)
    if settings.db_configured
    else None
)

SessionLocal = (
    sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    if engine is not None
    else None
)


def get_db() -> Iterator[Session]:
    if SessionLocal is None:
        raise RuntimeError("Database not configured (DATABASE_URL is empty).")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
