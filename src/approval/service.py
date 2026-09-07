"""Shared approval -> generation logic used by the webhook endpoint and the
local web dashboard (the Telegram bot has its own multi-step version of this
since it splits topic choice and format choice into two separate messages)."""
from __future__ import annotations
from fastapi import HTTPException

from src.models import GeneratedContent
from src.stores import approval_store, raw_content_store
from src.ai_brain.persona import load_persona
from src.generators.base import generate_content


def approve_and_generate(
    approval_id: str, topic_id: str, format_type: int, custom_prompt: str = ""
) -> GeneratedContent:
    approval = approval_store().get(approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")

    topic = next((t for t in approval.topics if t.id == topic_id), None)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found on this approval")

    approval.chosen_topic_id = topic.id
    approval.chosen_format = format_type
    approval.custom_prompt = custom_prompt
    approval.status = "approved"
    approval_store().update(approval)

    raw_content = raw_content_store().get(approval.content_id)
    persona = load_persona()
    return generate_content(format_type, topic, raw_content, persona, approval.id, custom_prompt)
