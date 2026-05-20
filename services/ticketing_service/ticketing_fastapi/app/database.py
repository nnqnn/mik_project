import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

BASE_DIR = Path(__file__).resolve().parent.parent
default_sync_url = f"sqlite:///{BASE_DIR / 'ticketing.db'}"
DATABASE_URL = os.getenv("DATABASE_URL", default_sync_url)

if DATABASE_URL.startswith("sqlite+aiosqlite:///"):
    ASYNC_DATABASE_URL = DATABASE_URL
    SYNC_DATABASE_URL = DATABASE_URL.replace("sqlite+aiosqlite:///", "sqlite:///")
elif DATABASE_URL.startswith("sqlite:///"):
    SYNC_DATABASE_URL = DATABASE_URL
    ASYNC_DATABASE_URL = DATABASE_URL.replace("sqlite:///", "sqlite+aiosqlite:///")
else:
    SYNC_DATABASE_URL = DATABASE_URL
    ASYNC_DATABASE_URL = DATABASE_URL

sync_connect_args = {"check_same_thread": False} if SYNC_DATABASE_URL.startswith("sqlite") else {}
engine = create_async_engine(ASYNC_DATABASE_URL, future=True, echo=False)
sync_engine = create_engine(SYNC_DATABASE_URL, connect_args=sync_connect_args)

SessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def ensure_schema() -> None:
    """Create required tables if they do not exist.

    Ticketing keeps only booking tables locally. We intentionally avoid a hard
    startup dependency on Alembic so container startup is deterministic.
    """
    Base.metadata.create_all(bind=sync_engine)
