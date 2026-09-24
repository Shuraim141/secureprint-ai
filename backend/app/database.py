"""Database engine/session setup (SQLAlchemy 2.0). SQLite for the MVP.

Production: set DATABASE_URL to PostgreSQL; only the SQLite PRAGMA block is dialect-specific.
"""
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings
from app.hardware import get_hardware_profile


class Base(DeclarativeBase):
    pass


def _build_engine(url: str):
    is_sqlite = url.startswith("sqlite")
    connect_args = {}
    if is_sqlite:
        db_file = make_url(url).database
        if db_file and db_file != ":memory:":
            Path(db_file).parent.mkdir(parents=True, exist_ok=True)
        connect_args["check_same_thread"] = False  # FastAPI uses a threadpool
    engine = create_engine(url, connect_args=connect_args)

    if is_sqlite:
        cache_kb = get_hardware_profile(get_settings().hardware_profile).sqlite_cache_kb

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute(f"PRAGMA cache_size=-{int(cache_kb)}")
            cursor.close()

    return engine


engine = _build_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables (idempotent). Importing app.models registers every table."""
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
