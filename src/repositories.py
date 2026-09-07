"""User-scoped data access. Replaces the old JSON-file `stores.py` / `storage.py`.

Every method takes an explicit `user_id` so a request can only ever read or
write its own rows. Cross-user reads (the scheduler, the channel-watch loop)
are isolated in the clearly-named `*_all_*` helpers at the bottom.
"""
from __future__ import annotations
import time
from typing import Generic, Optional, Type, TypeVar

from sqlmodel import Session, select

from src.models import (
    ApprovalRequest,
    FacebookConnection,
    GeneratedContent,
    Persona,
    PersonaData,
    RawContent,
    WatchConfig,
    WordPressConnection,
)

T = TypeVar("T")


class Repo(Generic[T]):
    """Generic CRUD for a table that has `id` + `user_id` columns."""

    def __init__(self, model: Type[T]):
        self.model = model

    def get(self, session: Session, user_id: str, item_id: str) -> Optional[T]:
        obj = session.get(self.model, item_id)
        if obj is None or obj.user_id != user_id:
            return None
        return obj

    def list(self, session: Session, user_id: str) -> list[T]:
        stmt = select(self.model).where(self.model.user_id == user_id)
        return list(session.exec(stmt).all())

    def add(self, session: Session, obj: T) -> T:
        session.add(obj)
        session.commit()
        session.refresh(obj)
        return obj

    def update(self, session: Session, obj: T) -> T:
        session.add(obj)
        session.commit()
        session.refresh(obj)
        return obj

    def delete(self, session: Session, user_id: str, item_id: str) -> bool:
        obj = self.get(session, user_id, item_id)
        if obj is None:
            return False
        session.delete(obj)
        session.commit()
        return True


raw_content_repo: Repo[RawContent] = Repo(RawContent)
approval_repo: Repo[ApprovalRequest] = Repo(ApprovalRequest)
generated_repo: Repo[GeneratedContent] = Repo(GeneratedContent)
facebook_repo: Repo[FacebookConnection] = Repo(FacebookConnection)
wordpress_repo: Repo[WordPressConnection] = Repo(WordPressConnection)


# --- Singleton-per-user rows: persona + watch config ----------------------


def get_or_create_persona(session: Session, user_id: str) -> Persona:
    persona = session.exec(select(Persona).where(Persona.user_id == user_id)).first()
    if persona is None:
        persona = Persona(user_id=user_id)
        session.add(persona)
        session.commit()
        session.refresh(persona)
    return persona


def save_persona_data(session: Session, user_id: str, data: PersonaData) -> Persona:
    persona = get_or_create_persona(session, user_id)
    persona.apply(data)
    session.add(persona)
    session.commit()
    session.refresh(persona)
    return persona


def get_or_create_watch_config(session: Session, user_id: str) -> WatchConfig:
    cfg = session.exec(select(WatchConfig).where(WatchConfig.user_id == user_id)).first()
    if cfg is None:
        cfg = WatchConfig(user_id=user_id)
        session.add(cfg)
        session.commit()
        session.refresh(cfg)
    return cfg


def get_facebook_connection(session: Session, user_id: str) -> Optional[FacebookConnection]:
    stmt = (
        select(FacebookConnection)
        .where(FacebookConnection.user_id == user_id)
        .order_by(FacebookConnection.created_at.desc())
    )
    return session.exec(stmt).first()


def get_wordpress_connection(session: Session, user_id: str) -> Optional[WordPressConnection]:
    stmt = (
        select(WordPressConnection)
        .where(WordPressConnection.user_id == user_id)
        .order_by(WordPressConnection.created_at.desc())
    )
    return session.exec(stmt).first()


# --- Cross-user reads (background jobs only) ------------------------------


def list_all_due_generated(session: Session, now: Optional[float] = None) -> list[GeneratedContent]:
    now = now or time.time()
    stmt = select(GeneratedContent).where(
        GeneratedContent.status == "draft",
        GeneratedContent.scheduled_at.is_not(None),
        GeneratedContent.scheduled_at <= now,
    )
    return list(session.exec(stmt).all())


def list_all_enabled_watch_configs(session: Session) -> list[WatchConfig]:
    stmt = select(WatchConfig).where(WatchConfig.enabled == True)  # noqa: E712
    return list(session.exec(stmt).all())
