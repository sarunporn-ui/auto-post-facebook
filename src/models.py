"""SQLModel tables + nested DTOs shared across modules.

Every user-owned row carries a `user_id` (FK to `users.id`). Nested/repeated
structures (topic lists, `extra` blobs, string lists) are stored as JSON columns
and wrapped in SQLAlchemy Mutable* types so in-place edits are still tracked.
"""
from __future__ import annotations
import time
import uuid
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import Column
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlmodel import JSON, Field, SQLModel


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _json_list() -> Column:
    return Column(MutableList.as_mutable(JSON))


def _json_dict() -> Column:
    return Column(MutableDict.as_mutable(JSON))


# --- Nested DTOs (not tables) ------------------------------------------------


class ContentTopic(BaseModel):
    id: str = Field(default_factory=_new_id)
    title: str
    preview: str
    core_takeaway: str


class PersonaData(BaseModel):
    """Plain-data view of a persona — what the dashboard sends/receives and what
    the LLM prompt builder consumes. Persisted via the `Persona` table row."""

    persona_name: str = ""
    language: str = "Thai"
    description: str = ""
    demographics: str = ""
    pain_points: list[str] = Field(default_factory=list)
    goals: list[str] = Field(default_factory=list)
    tone_of_voice: str = ""
    content_pillars: list[str] = Field(default_factory=list)
    forbidden_topics: list[str] = Field(default_factory=list)
    preferred_cta: str = ""


# --- Tables ----------------------------------------------------------------


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: str = Field(primary_key=True)  # == Supabase auth.users.id (uuid string)
    email: str = Field(index=True)
    created_at: float = Field(default_factory=time.time)


class Persona(SQLModel, table=True):
    __tablename__ = "personas"

    id: str = Field(default_factory=_new_id, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True, unique=True)
    persona_name: str = ""
    language: str = "Thai"
    description: str = ""
    demographics: str = ""
    pain_points: list[str] = Field(default_factory=list, sa_column=_json_list())
    goals: list[str] = Field(default_factory=list, sa_column=_json_list())
    tone_of_voice: str = ""
    content_pillars: list[str] = Field(default_factory=list, sa_column=_json_list())
    forbidden_topics: list[str] = Field(default_factory=list, sa_column=_json_list())
    preferred_cta: str = ""
    updated_at: float = Field(default_factory=time.time)

    def to_data(self) -> PersonaData:
        return PersonaData(
            persona_name=self.persona_name,
            language=self.language,
            description=self.description,
            demographics=self.demographics,
            pain_points=list(self.pain_points or []),
            goals=list(self.goals or []),
            tone_of_voice=self.tone_of_voice,
            content_pillars=list(self.content_pillars or []),
            forbidden_topics=list(self.forbidden_topics or []),
            preferred_cta=self.preferred_cta,
        )

    def apply(self, data: PersonaData) -> None:
        for field, value in data.model_dump().items():
            setattr(self, field, value)
        self.updated_at = time.time()


class RawContent(SQLModel, table=True):
    __tablename__ = "raw_content"

    id: str = Field(default_factory=_new_id, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    source_type: str = ""  # youtube | facebook | text
    source_url: Optional[str] = None
    title: str = ""
    raw_text: str
    created_at: float = Field(default_factory=time.time)
    meta: dict = Field(default_factory=dict, sa_column=_json_dict())  # was `metadata` (reserved)


class ApprovalRequest(SQLModel, table=True):
    __tablename__ = "approval_requests"

    id: str = Field(default_factory=_new_id, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    content_id: str = Field(index=True)
    topics: list[dict] = Field(default_factory=list, sa_column=_json_list())
    status: str = "pending"  # pending | topic_selected | approved | rejected
    chosen_topic_id: Optional[str] = None
    chosen_format: Optional[int] = None
    custom_prompt: str = ""
    created_at: float = Field(default_factory=time.time)

    def topic_models(self) -> list[ContentTopic]:
        return [ContentTopic(**t) for t in (self.topics or [])]


class GeneratedContent(SQLModel, table=True):
    __tablename__ = "generated_content"

    id: str = Field(default_factory=_new_id, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    approval_id: str = Field(index=True)
    content_id: str = Field(index=True)
    format_type: int
    title: str = ""
    body: str = ""
    extra: dict = Field(default_factory=dict, sa_column=_json_dict())  # image_prompt/url, pdf_url
    status: str = "draft"  # draft | published
    scheduled_at: Optional[float] = None
    scheduled_channels: list[str] = Field(default_factory=list, sa_column=_json_list())
    schedule_error: Optional[str] = None
    created_at: float = Field(default_factory=time.time)


class WatchConfig(SQLModel, table=True):
    __tablename__ = "watch_configs"

    id: str = Field(default_factory=_new_id, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True, unique=True)
    enabled: bool = False
    channel_url: str = ""
    check_interval_hours: int = 24
    last_checked_at: Optional[float] = None
    seen_video_ids: list[str] = Field(default_factory=list, sa_column=_json_list())


class FacebookConnection(SQLModel, table=True):
    __tablename__ = "facebook_connections"

    id: str = Field(default_factory=_new_id, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    page_id: str
    page_name: str = ""
    encrypted_page_token: str = ""
    token_created_at: float = Field(default_factory=time.time)
    scopes: str = ""
    created_at: float = Field(default_factory=time.time)


class WordPressConnection(SQLModel, table=True):
    __tablename__ = "wordpress_connections"

    id: str = Field(default_factory=_new_id, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    site_url: str
    username: str = ""
    encrypted_app_password: str = ""
    created_at: float = Field(default_factory=time.time)


class FacebookOAuthFlow(SQLModel, table=True):
    """Short-lived scratch row for one in-progress 'Connect Facebook' handshake.
    Holds the CSRF `state` and, after the callback, the encrypted list of the
    user's Pages (each with its own Page token) until they pick one."""

    __tablename__ = "facebook_oauth_flows"

    user_id: str = Field(foreign_key="users.id", primary_key=True)
    state: str = Field(index=True)
    encrypted_pages_json: str = ""  # [{"id","name","access_token"}, ...] once the callback ran
    created_at: float = Field(default_factory=time.time)
