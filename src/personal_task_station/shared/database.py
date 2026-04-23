from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .settings import AppSettings


class Base(DeclarativeBase):
    """Base declarative metadata."""


def create_sqlite_engine(database_url: str):
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(database_url, connect_args=connect_args, future=True)


def ensure_sqlite_parent(database_url: str) -> None:
    if not database_url.startswith("sqlite:///"):
        return
    path = Path(database_url.replace("sqlite:///", "", 1))
    path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=8)
def get_engine(database_url: str | None = None):
    selected_url = database_url or AppSettings.load().database_url
    ensure_sqlite_parent(selected_url)
    return create_sqlite_engine(selected_url)


@lru_cache(maxsize=8)
def get_session_factory(database_url: str | None = None):
    return sessionmaker(
        bind=get_engine(database_url),
        autoflush=False,
        autocommit=False,
        future=True,
    )


def reset_database_caches() -> None:
    get_session_factory.cache_clear()
    get_engine.cache_clear()


def get_session(database_url: str | None = None) -> Generator[Session, None, None]:
    session = get_session_factory(database_url)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def session_scope(database_url: str | None = None) -> Generator[Session, None, None]:
    session = get_session_factory(database_url)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
