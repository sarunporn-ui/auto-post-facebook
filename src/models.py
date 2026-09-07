"""Pydantic data models shared across modules."""
from __future__ import annotations
import time
import uuid
from typing import Literal, Optional

from pydantic import BaseModel, Field


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


class RawContent(BaseModel):
    id: str = Field(default_factory=_new_id)
    source_type: Literal["youtube", "facebook", "text"]
    source_url: Optional[str] = None
    title: str = ""
    raw_text: str
    created_at: float = Field(default_factory=time.time)
    metadata: dict = Field(default_factory=dict)


class Persona(BaseModel):
    persona_name: str
    language: str = "Thai"
    description: str = ""
    demographics: str = ""
    pain_points: list[str] = Field(default_factory=list)
    goals: list[str] = Field(default_factory=list)
    tone_of_voice: str = ""
    content_pillars: list[str] = Field(default_factory=list)
    forbidden_topics: list[str] = Field(default_factory=list)
    preferred_cta: str = ""


class ContentTopic(BaseModel):
    id: str = Field(default_factory=_new_id)
    title: str
    preview: str
    core_takeaway: str


class ApprovalRequest(BaseModel):
    id: str = Field(default_factory=_new_id)
    content_id: str
    topics: list[ContentTopic]
    status: Literal["pending", "topic_selected", "approved", "rejected"] = "pending"
    chosen_topic_id: Optional[str] = None
    chosen_format: Optional[int] = None
    custom_prompt: str = ""
    telegram_chat_id: Optional[str] = None
    telegram_message_id: Optional[int] = None
    created_at: float = Field(default_factory=time.time)


class WatchConfig(BaseModel):
    enabled: bool = False
    channel_url: str = ""
    check_interval_hours: int = 24
    last_checked_at: Optional[float] = None
    seen_video_ids: list[str] = Field(default_factory=list)


class GeneratedContent(BaseModel):
    id: str = Field(default_factory=_new_id)
    approval_id: str
    content_id: str
    format_type: int
    title: str = ""
    body: str = ""
    extra: dict = Field(default_factory=dict)  # e.g. image_prompt, image_path, pdf_path
    status: Literal["draft", "published"] = "draft"
    scheduled_at: Optional[float] = None
    scheduled_channels: list[str] = Field(default_factory=list)
    schedule_error: Optional[str] = None
    created_at: float = Field(default_factory=time.time)
