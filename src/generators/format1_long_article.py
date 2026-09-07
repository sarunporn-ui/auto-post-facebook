"""Format 1 — SEO-friendly long-form article for the website (H1/H2/H3 + TOC + CTA)."""
from __future__ import annotations

from src.models import ContentTopic, RawContent
from src.ai_brain.llm_client import complete
from src.ai_brain.persona import persona_prompt_block

SYSTEM_PROMPT = (
    "You are an SEO content writer producing publish-ready long-form articles in Markdown."
)

PROMPT_TEMPLATE = """\
{persona_block}

Topic: {title}
Angle: {preview}
Core takeaway to build the article around: {core_takeaway}

Source material excerpt for factual grounding:
\"\"\"
{raw_excerpt}
\"\"\"

{custom_instructions}

Write a complete SEO-friendly long-form article in Markdown with:
- One H1 title (compelling, keyword-aware)
- A short intro paragraph
- A "Table of Contents" section linking to each H2
- Multiple H2 sections, with H3 subsections where useful
- A concluding section with a clear call-to-action matching the persona's preferred CTA style

Write the entire article — including the H1, headings, and body — in the OUTPUT
LANGUAGE specified above. Output only the Markdown article, nothing else.
"""


def generate(topic: ContentTopic, raw_content: RawContent, persona: dict, custom_prompt: str = ""):
    custom_instructions = f"Additional style/tone instructions: {custom_prompt}" if custom_prompt else ""
    prompt = PROMPT_TEMPLATE.format(
        persona_block=persona_prompt_block(persona),
        title=topic.title,
        preview=topic.preview,
        core_takeaway=topic.core_takeaway,
        raw_excerpt=raw_content.raw_text[:6000],
        custom_instructions=custom_instructions,
    )
    body = complete(SYSTEM_PROMPT, prompt, json_mode=False)
    return topic.title, body, {}
