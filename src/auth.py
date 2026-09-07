"""Request authentication.

Phase 2 will verify a real Supabase Auth JWT here. For now, when
`SUPABASE_JWT_SECRET` is unset the app runs in single-user dev mode against a
fixed local user, so the rest of the stack (repositories, per-user rows) can be
built and tested. The dependency signature (`current_user: User`) stays stable
across both modes.
"""
from __future__ import annotations
import json
import logging

import jwt
from fastapi import Depends, Header, HTTPException
from sqlmodel import Session

from src.config import get_settings
from src.db import get_session
from src.models import Persona, PersonaData, User

logger = logging.getLogger(__name__)


def _seed_persona_from_template(session: Session, user_id: str) -> None:
    if session.get(Persona, user_id) is not None:
        return
    from sqlmodel import select

    if session.exec(select(Persona).where(Persona.user_id == user_id)).first() is not None:
        return

    settings = get_settings()
    data = PersonaData()
    try:
        if settings.persona_template_file.exists():
            raw = json.loads(settings.persona_template_file.read_text(encoding="utf-8"))
            data = PersonaData(**{k: v for k, v in raw.items() if k in PersonaData.model_fields})
    except Exception:
        logger.exception("Could not load persona template; seeding an empty persona")

    persona = Persona(user_id=user_id)
    persona.apply(data)
    session.add(persona)
    session.commit()


def _get_or_create_user(session: Session, user_id: str, email: str) -> User:
    user = session.get(User, user_id)
    if user is None:
        user = User(id=user_id, email=email)
        session.add(user)
        session.commit()
        session.refresh(user)
        _seed_persona_from_template(session, user_id)
    return user


def get_current_user(
    session: Session = Depends(get_session),
    authorization: str | None = Header(default=None),
) -> User:
    settings = get_settings()

    # --- Dev mode: no Supabase secret configured -> fixed local user ---
    if not settings.supabase_jwt_secret:
        return _get_or_create_user(session, settings.dev_user_id, settings.dev_user_email)

    # --- Real mode: verify the Supabase access token ---
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        claims = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}") from exc

    user_id = claims.get("sub")
    email = claims.get("email") or claims.get("user_metadata", {}).get("email", "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token has no subject")
    return _get_or_create_user(session, user_id, email)


CurrentUser = Depends(get_current_user)
