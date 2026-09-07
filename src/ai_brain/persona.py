"""Loads and saves the Target Persona definition used to steer every LLM prompt.

The persona is meant to be editable anytime from the dashboard's Persona
section, so it's read fresh from disk on every call rather than cached.
"""
import json

from src.config import get_settings
from src.models import Persona


def load_persona() -> dict:
    settings = get_settings()
    if not settings.persona_file.exists():
        raise FileNotFoundError(
            f"Persona file not found at {settings.persona_file}. "
            "Set one via the dashboard, or copy/edit target_persona.json at the project root."
        )
    return json.loads(settings.persona_file.read_text(encoding="utf-8"))


def save_persona(persona: Persona) -> dict:
    settings = get_settings()
    data = persona.model_dump()
    settings.persona_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return data


def persona_prompt_block(persona: dict | None = None) -> str:
    """Render the persona as a compact text block for inclusion in LLM prompts."""
    persona = persona or load_persona()
    return (
        f"Persona: {persona.get('persona_name')}\n"
        f"OUTPUT LANGUAGE: {persona.get('language', 'Thai')} — write everything in this "
        f"language: all titles, previews, takeaways, and body copy. JSON keys stay in "
        f"English exactly as instructed; only the text values are in this language.\n"
        f"Description: {persona.get('description')}\n"
        f"Demographics: {persona.get('demographics')}\n"
        f"Pain points: {', '.join(persona.get('pain_points', []))}\n"
        f"Goals: {', '.join(persona.get('goals', []))}\n"
        f"Tone of voice: {persona.get('tone_of_voice')}\n"
        f"Content pillars: {', '.join(persona.get('content_pillars', []))}\n"
        f"Preferred CTA style: {persona.get('preferred_cta')}\n"
        f"Topics/angles to avoid: {', '.join(persona.get('forbidden_topics', []))}"
    )
