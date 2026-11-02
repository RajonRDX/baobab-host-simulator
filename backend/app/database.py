"""
MODULE 1 — database.py
Database connection, SQLAlchemy session management, base configuration, and initialization.
Supports PostgreSQL (Neon/local) and SQLite for zero-config local Windows testing.
"""

from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from app.config import settings

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine_kwargs = {}
if settings.DATABASE_URL.startswith("sqlite") and ":memory:" in settings.DATABASE_URL:
    # in-memory SQLite is per-connection; share one connection across threads (tests)
    from sqlalchemy.pool import StaticPool
    engine_kwargs["poolclass"] = StaticPool

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    future=True,
    **engine_kwargs,
)

if settings.DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# [PATCH step00_02:database_sync_schema]
def init_db() -> None:
    import app.models  # noqa: F401
    from app.schema_sync import synchronize_database_schema
    synchronize_database_schema(engine, Base)
# [PATCH tx_log_viewer_v3:ensure_tx_log_indexes]
    from app.database_indexes_tx_logs import ensure_transaction_log_indexes
    ensure_transaction_log_indexes(engine)
