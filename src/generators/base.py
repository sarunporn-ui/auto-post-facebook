"""Registry + dispatcher for the 5 content-format generators."""
from __future__ import annotations
from typing import Callable

from sqlmodel import Session

from src.models import ContentTopic, RawContent, GeneratedContent
from src.repositories import generated_repo

from src.generators import (
    format1_long_article,
    format2_social_post,
    format3_fb_offer,
    format4_pdf_leadmagnet,
    format5_tiktok_script,
)

GENERATORS: dict[int, Callable] = {
    1: format1_long_article.generate,
    2: format2_social_post.generate,
    3: format3_fb_offer.generate,
    4: format4_pdf_leadmagnet.generate,
    5: format5_tiktok_script.generate,
}

FORMAT_NAMES = {
    1: "Website Long-Form Article",
    2: "Short Social Post + Image Prompt",
    3: "Facebook Offer Post",
    4: "PDF Lead Magnet",
    5: "TikTok 60s Script",
}


def generate_content(
    session: Session,
    user_id: str,
    format_type: int,
    topic: ContentTopic,
    raw_content: RawContent,
    persona: dict,
    approval_id: str,
    custom_prompt: str = "",
) -> GeneratedContent:
    if format_type not in GENERATORS:
        raise ValueError(f"Unknown format_type: {format_type}. Must be 1-5.")

    title, body, extra = GENERATORS[format_type](topic, raw_content, persona, custom_prompt)

    generated = GeneratedContent(
        user_id=user_id,
        approval_id=approval_id,
        content_id=raw_content.id,
        format_type=format_type,
        title=title,
        body=body,
        extra=extra,
    )
    return generated_repo.add(session, generated)
