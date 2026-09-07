"""Shared approval -> generation logic used by the dashboard API and the webhook."""
from __future__ import annotations
from fastapi import HTTPException
from sqlmodel import Session

from src.models import GeneratedContent
from src.repositories import approval_repo, raw_content_repo
from src.ai_brain.persona import load_persona
from src.generators.base import generate_content


def approve_and_generate(
    session: Session,
    user_id: str,
    approval_id: str,
    topic_id: str,
    format_type: int,
    custom_prompt: str = "",
) -> GeneratedContent:
    approval = approval_repo.get(session, user_id, approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")

    topic = next((t for t in approval.topic_models() if t.id == topic_id), None)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found on this approval")

    approval.chosen_topic_id = topic.id
    approval.chosen_format = format_type
    approval.custom_prompt = custom_prompt
    approval.status = "approved"
    approval_repo.update(session, approval)

    raw_content = raw_content_repo.get(session, user_id, approval.content_id)
    if not raw_content:
        raise HTTPException(status_code=404, detail="Source content not found")

    persona = load_persona(session, user_id)
    return generate_content(
        session, user_id, format_type, topic, raw_content, persona, approval.id, custom_prompt
    )
