"""Per-user Target Persona: loaded from the DB row, injected into every LLM prompt.

`target_persona.json` at the project root is now only a *template* used to seed a
new user's persona on first login (see `src/auth.py`).
"""
from __future__ import annotations

from sqlmodel import Session

from src.models import PersonaData
from src.repositories import get_or_create_persona, save_persona_data


def load_persona(session: Session, user_id: str) -> dict:
    return get_or_create_persona(session, user_id).to_data().model_dump()


def save_persona(session: Session, user_id: str, data: PersonaData) -> dict:
    return save_persona_data(session, user_id, data).to_data().model_dump()


def persona_prompt_block(persona: dict) -> str:
    """Render the persona as a compact text block for inclusion in LLM prompts."""
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
