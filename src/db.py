"""Database engine + session management.

`DATABASE_URL` drives everything:
  - local dev  -> sqlite:///<data_dir>/content_os.db  (default)
  - production -> Supabase Postgres pooler URL (postgresql+psycopg://...)

The rest of the app never touches SQLAlchemy directly — it goes through
`get_session` (FastAPI dependency) or `session_scope` (background loops), plus
the repositories in `src/repositories.py`.
"""
from __future__ import annotations
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel

from src.config import get_settings

# Import models so SQLModel.metadata is populated before create_all().
from src import models  # noqa: F401


def _make_engine():
    settings = get_settings()
    url = settings.database_url
    connect_args = {}
    kwargs = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    else:
        # Supabase pooler: keep the client pool small, recycle before Postgres
        # times connections out.
        kwargs.update(pool_size=5, max_overflow=5, pool_recycle=1800)
    return create_engine(url, connect_args=connect_args, **kwargs)


engine = _make_engine()


def init_db() -> None:
    """Create any missing tables. Safe to call on every startup."""
    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency — one session per request."""
    with Session(engine) as session:
        yield session


@contextmanager
def session_scope() -> Iterator[Session]:
    """For code outside the request cycle (background loops, scripts)."""
    with Session(engine) as session:
        yield session
