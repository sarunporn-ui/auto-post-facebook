"""FastAPI webhook — a REST alternative to the dashboard for approving
topics/formats from an external automation (Airtable/Zapier)."""
from __future__ import annotations
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from src.config import get_settings
from src.db import get_session
from src.approval.service import approve_and_generate

router = APIRouter(prefix="/webhook", tags=["approval"])


class ApproveRequest(BaseModel):
    user_id: str
    approval_id: str
    topic_id: str
    format_type: int
    custom_prompt: str = ""


def _check_secret(x_webhook_secret: str | None) -> None:
    settings = get_settings()
    if x_webhook_secret != settings.approval_webhook_secret:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")


@router.post("/approve")
def approve(
    payload: ApproveRequest,
    session: Session = Depends(get_session),
    x_webhook_secret: str | None = Header(default=None),
):
    _check_secret(x_webhook_secret)
    generated = approve_and_generate(
        session,
        payload.user_id,
        payload.approval_id,
        payload.topic_id,
        payload.format_type,
        payload.custom_prompt,
    )
    return {"generated_content_id": generated.id, "status": generated.status}
