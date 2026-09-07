"""Format 3 — Facebook offer post structured as Problem -> Solution -> Offer -> CTA."""
from __future__ import annotations

from src.models import ContentTopic, RawContent
from src.ai_brain.llm_client import complete
from src.ai_brain.persona import persona_prompt_block

SYSTEM_PROMPT = "You are a direct-response copywriter writing short Facebook offer posts."

PROMPT_TEMPLATE = """\
{persona_block}

Topic: {title}
Angle: {preview}
Core takeaway: {core_takeaway}

{custom_instructions}

Write a short Facebook post using exactly this structure, each part 1-3 sentences:
1. Problem — name the persona's pain point in a relatable way
2. Solution — the shift in thinking or approach that solves it
3. Offer — a free resource tied to the topic (e.g. a checklist, guide, or template)
4. CTA — ask the reader to comment a specific keyword to receive the offer
   (e.g. "Comment '99' below and I'll send it to you")

Write the whole post in the OUTPUT LANGUAGE specified above. Output plain text
only, formatted with line breaks between each section, no labels/headers.
"""


def generate(topic: ContentTopic, raw_content: RawContent, persona: dict, custom_prompt: str = ""):
    custom_instructions = f"Additional style/tone instructions: {custom_prompt}" if custom_prompt else ""
    prompt = PROMPT_TEMPLATE.format(
        persona_block=persona_prompt_block(persona),
        title=topic.title,
        preview=topic.preview,
        core_takeaway=topic.core_takeaway,
        custom_instructions=custom_instructions,
    )
    body = complete(SYSTEM_PROMPT, prompt, json_mode=False)
    return topic.title, body, {}
