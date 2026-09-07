"""Format 2 — high-converting short social post with a 3-second hook, plus a
matching image, actually generated via DALL-E from the image prompt."""
from __future__ import annotations
import logging

from src.models import ContentTopic, RawContent
from src.ai_brain.llm_client import complete, extract_json
from src.ai_brain.persona import persona_prompt_block
from src.generators.image_generator import generate_image

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a short-form social copywriter and an art director. You write "
    "punchy, scroll-stopping posts and precise image-generation prompts."
)

PROMPT_TEMPLATE = """\
{persona_block}

Topic: {title}
Angle: {preview}
Core takeaway: {core_takeaway}

{custom_instructions}

Write a short social media post (Instagram/Facebook/LinkedIn style) with:
- A hook in the first line that grabs attention in under 3 seconds
- Short lines and clean line-break spacing (no dense paragraphs)
- A natural closing line that invites engagement

Also write one image-generation prompt (for Flux or DALL-E) that would produce
a scroll-stopping visual to accompany this post.

Respond ONLY with JSON of this shape. Write "post_text" in the OUTPUT LANGUAGE
specified above. Write "image_prompt" in English regardless of the output
language — image-generation models work best with English prompts:
{{"post_text": "...", "image_prompt": "..."}}
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
    raw = complete(SYSTEM_PROMPT, prompt, json_mode=True)
    data = extract_json(raw)
    image_prompt = data.get("image_prompt", "")

    extra = {"image_prompt": image_prompt}
    if image_prompt:
        try:
            extra["image_path"] = generate_image(image_prompt)
        except Exception:
            # Image generation is best-effort (e.g. OPENAI_API_KEY not set yet) —
            # the post text and prompt are still useful without a rendered image.
            logger.exception("Image generation failed; continuing without an image")

    return topic.title, data["post_text"], extra
