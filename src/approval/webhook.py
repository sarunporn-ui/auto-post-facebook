"""FastAPI webhook — an alternative to Telegram/dashboard for approving
topics/formats (e.g. from an external automation like Airtable/Zapier)."""
from __future__ import annotations
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from src.config import get_settings
from src.approval.service import approve_and_generate

router = APIRouter(prefix="/webhook", tags=["approval"])


class ApproveRequest(BaseModel):
    approval_id: str
    topic_id: str
    format_type: int
    custom_prompt: str = ""


def _check_secret(x_webhook_secret: str | None) -> None:
    settings = get_settings()
    if x_webhook_secret != settings.approval_webhook_secret:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")


@router.post("/approve")
def approve(payload: ApproveRequest, x_webhook_secret: str | None = Header(default=None)):
    _check_secret(x_webhook_secret)
    generated = approve_and_generate(
        payload.approval_id, payload.topic_id, payload.format_type, payload.custom_prompt
    )
    return {"generated_content_id": generated.id, "status": generated.status}
