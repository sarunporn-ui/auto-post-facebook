"""Database engine + session management.

`DATABASE_URL` drives everything:
  - local dev  -> sqlite:///<data_dir>/content_os.db  (default)
  - production -> Supabase Postgres pooler URL (postgresql+psycopg://...)

The rest of the app never touches SQLAlchemy directly — it goes through
`get_session` (FastAPI dependency) or `session_scope` (background loops), plus
the repositories in `src/repositories.py`.
"""
from __future__ import annotations
import logging
from contextlib import contextmanager
from typing import Iterator
from urllib.parse import quote

from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel

from src.config import get_settings

# Import models so SQLModel.metadata is populated before create_all().
from src import models  # noqa: F401

logger = logging.getLogger(__name__)

# Characters that break SQLAlchemy's URL parser if they appear raw in a DB
# password. `%` is deliberately excluded so an already-encoded password is left
# alone (re-encoding would turn %40 into %2540).
_PW_UNSAFE = set("@/?#[]: ")


def normalize_db_url(raw: str) -> str:
    """Make a hand-pasted DATABASE_URL robust:
    - strip quotes/whitespace and a stray `psql ` prefix
    - `postgres://` / `postgresql://` -> `postgresql+psycopg://`
    - percent-encode a password that contains raw unsafe characters
      (leaves an already-encoded password untouched)
    """
    url = raw.strip().strip('"').strip("'").strip()
    if url.lower().startswith("psql "):
        url = url[5:].strip().strip('"').strip("'")

    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]

    if "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "@" not in rest:
        return url

    userinfo, hostpart = rest.rsplit("@", 1)
    if ":" in userinfo:
        user, pw = userinfo.split(":", 1)
        if any(c in _PW_UNSAFE for c in pw):
            pw = quote(pw, safe="")
        userinfo = f"{user}:{pw}"
    return f"{scheme}://{userinfo}@{hostpart}"


def _make_engine():
    settings = get_settings()
    url = normalize_db_url(settings.database_url)
    connect_args = {}
    kwargs = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    else:
        # Supabase pooler: keep the client pool small, recycle before Postgres
        # times connections out.
        kwargs.update(pool_size=5, max_overflow=5, pool_recycle=1800)
    try:
        return create_engine(url, connect_args=connect_args, **kwargs)
    except Exception:
        # Log a redacted form so a bad DATABASE_URL is diagnosable without
        # leaking the password.
        redacted = url
        if "://" in redacted and "@" in redacted:
            head, tail = redacted.split("://", 1)
            userinfo, hostpart = tail.rsplit("@", 1)
            user = userinfo.split(":", 1)[0]
            redacted = f"{head}://{user}:***@{hostpart}"
        logger.error("Failed to build DB engine from DATABASE_URL=%s", redacted)
        raise


engine = _make_engine()


def init_db() -> None:
    """Create any missing tables. Safe to call on every startup."""
    settings = get_settings()
    if normalize_db_url(settings.database_url).startswith("sqlite"):
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
