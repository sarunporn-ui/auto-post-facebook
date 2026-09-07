"""Format 5 — 60-second TikTok script with a timestamped hook/curiosity/problem/solution/CTA structure."""
from __future__ import annotations

from src.models import ContentTopic, RawContent
from src.ai_brain.llm_client import complete
from src.ai_brain.persona import persona_prompt_block

SYSTEM_PROMPT = "You are a short-form video scriptwriter for TikTok/Reels/Shorts."

PROMPT_TEMPLATE = """\
{persona_block}

Topic: {title}
Angle: {preview}
Core takeaway: {core_takeaway}

{custom_instructions}

Write a 60-second vertical video script using exactly this beat structure:
[0-3s Hook] - a scroll-stopping opening line
[3-10s Curiosity] - build intrigue, tease what's coming
[10-25s Problem] - name the persona's pain point
[25-35s Solution/Tips] - the core insight or tip
[35-60s CTA] - a strong call to action matching the persona's preferred CTA style

Output as plain text, one labelled section per beat exactly as shown above.
Keep the bracketed timestamp labels exactly as shown; write the on-camera
line(s) under each label in the OUTPUT LANGUAGE specified above.
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
