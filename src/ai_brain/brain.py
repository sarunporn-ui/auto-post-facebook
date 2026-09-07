"""Core AI Brain: turns raw ingested content into persona-matched content topic ideas."""
from __future__ import annotations

from src.models import RawContent, ContentTopic
from src.ai_brain.llm_client import complete, extract_json
from src.ai_brain.persona import persona_prompt_block

SYSTEM_PROMPT = (
    "You are a senior content strategist. You read raw source material (a video "
    "transcript or social post) and translate it into content ideas tailored "
    "exactly to a given target persona. You never invent facts that are not "
    "supported by the source material."
)

TOPIC_PROMPT_TEMPLATE = """\
{persona_block}

SOURCE MATERIAL (raw transcript / post text):
\"\"\"
{raw_text}
\"\"\"

Task: Extract the core takeaways from the source material, then generate between
3 and 5 distinct content topic ideas that would resonate with the persona above.

Respond ONLY with a JSON object of this exact shape (keep the JSON keys in English
exactly as shown; write every text VALUE in the OUTPUT LANGUAGE specified above):
{{
  "core_takeaways": ["...", "..."],
  "topics": [
    {{"title": "...", "preview": "1-2 sentence teaser of the angle", "core_takeaway": "the single insight this topic is built on"}}
  ]
}}
"""


def analyze_content(
    raw_content: RawContent, persona: dict
) -> tuple[list[str], list[ContentTopic]]:
    """Analyze raw content against the target persona and return (takeaways, topics)."""
    prompt = TOPIC_PROMPT_TEMPLATE.format(
        persona_block=persona_prompt_block(persona),
        raw_text=raw_content.raw_text[:12000],  # keep prompt within context budget
    )
    raw_response = complete(SYSTEM_PROMPT, prompt, json_mode=True)
    data = extract_json(raw_response)
    topics = [ContentTopic(**t) for t in data.get("topics", [])][:5]
    return data.get("core_takeaways", []), topics
