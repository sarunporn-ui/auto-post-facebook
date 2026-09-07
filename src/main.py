"""FastAPI application: orchestrates ingestion -> AI analysis -> human approval
-> multi-format generation -> publishing.

Run with:  uvicorn src.main:app --reload
Then open http://localhost:8000/dashboard in a browser to use the approval UI.

The Telegram bot (src/approval/telegram_bot.py) is an optional alternative
approval interface — run it as its own process if you'd rather approve from
your phone instead of the local dashboard.
"""
from __future__ import annotations
import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.models import ApprovalRequest, Persona
from src.stores import raw_content_store, approval_store, generated_content_store
from src.ingestion.youtube_ingestor import ingest_youtube
from src.ingestion.facebook_ingestor import ingest_facebook
from src.ai_brain.brain import analyze_content
from src.ai_brain.persona import load_persona, save_persona
from src.approval.webhook import router as approval_router
from src.approval.service import approve_and_generate
from src.publisher.facebook_publisher import publish_to_facebook
from src.publisher.wordpress_publisher import publish_to_wordpress
from src.watch_service import load_watch_config, save_watch_config, check_and_ingest_new_videos

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

logger = logging.getLogger(__name__)

# Wake every 5 minutes; only actually scans the channel when the configured
# interval has elapsed. Keeps "just enabled it" responsive without a restart.
_WATCH_POLL_SECONDS = 300


async def _watch_loop() -> None:
    while True:
        try:
            config = load_watch_config()
            if config.enabled and config.channel_url:
                due = config.last_checked_at is None or (
                    time.time() - config.last_checked_at >= config.check_interval_hours * 3600
                )
                if due:
                    await asyncio.to_thread(check_and_ingest_new_videos)
        except Exception:
            logger.exception("Channel watch loop iteration failed")
        await asyncio.sleep(_WATCH_POLL_SECONDS)


_SCHEDULE_POLL_SECONDS = 60


def _publish_due_scheduled_items() -> None:
    now = time.time()
    for generated in generated_content_store().list():
        if generated.status != "draft" or not generated.scheduled_at:
            continue
        if generated.scheduled_at > now:
            continue

        errors = []
        for channel in generated.scheduled_channels:
            try:
                if channel == "wordpress":
                    publish_to_wordpress(generated.title, generated.body, status="draft")
                elif channel == "facebook":
                    publish_to_facebook(generated.body)
            except Exception as exc:
                errors.append(f"{channel}: {exc}")

        if errors:
            # Don't retry-loop forever against a misconfigured/missing credential —
            # surface the error and let the user re-schedule once it's fixed.
            generated.schedule_error = "; ".join(errors)
            generated.scheduled_at = None
        else:
            generated.status = "published"
            generated.schedule_error = None
            generated.scheduled_at = None
            generated.scheduled_channels = []
        generated_content_store().update(generated)


async def _schedule_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(_publish_due_scheduled_items)
        except Exception:
            logger.exception("Schedule loop iteration failed")
        await asyncio.sleep(_SCHEDULE_POLL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    watch_task = asyncio.create_task(_watch_loop())
    schedule_task = asyncio.create_task(_schedule_loop())
    yield
    watch_task.cancel()
    schedule_task.cancel()


app = FastAPI(title="Automated Content OS", version="0.1.0", lifespan=lifespan)
app.include_router(approval_router)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


class YoutubeIngestRequest(BaseModel):
    url: str


class FacebookIngestRequest(BaseModel):
    url_or_text: str


class PublishRequest(BaseModel):
    channel: str  # "facebook" | "wordpress"


class DashboardGenerateRequest(BaseModel):
    approval_id: str
    topic_id: str
    format_type: int
    custom_prompt: str = ""


class WatchConfigInput(BaseModel):
    enabled: bool = False
    channel_url: str = ""
    check_interval_hours: int = 24


class ScheduleRequest(BaseModel):
    channels: list[str]
    scheduled_at: Optional[float] = None  # unix timestamp; omit/None clears the schedule


@app.get("/")
def root():
    return {"status": "ok", "service": "Automated Content OS", "dashboard": "/dashboard"}


@app.get("/dashboard")
def dashboard():
    return FileResponse(WEB_DIR / "index.html")


@app.post("/ingest/youtube")
def ingest_youtube_endpoint(payload: YoutubeIngestRequest):
    raw_content = ingest_youtube(payload.url)
    raw_content_store().save(raw_content)
    return raw_content


@app.post("/ingest/facebook")
def ingest_facebook_endpoint(payload: FacebookIngestRequest):
    raw_content = ingest_facebook(payload.url_or_text)
    raw_content_store().save(raw_content)
    return raw_content


@app.post("/analyze/{content_id}")
def analyze_endpoint(content_id: str):
    raw_content = raw_content_store().get(content_id)
    if not raw_content:
        raise HTTPException(status_code=404, detail="Raw content not found")

    persona = load_persona()
    takeaways, topics = analyze_content(raw_content, persona)
    if not topics:
        raise HTTPException(status_code=502, detail="AI Brain returned no topics")

    approval = ApprovalRequest(content_id=content_id, topics=topics)
    approval_store().save(approval)

    return {"approval_id": approval.id, "core_takeaways": takeaways, "topics": topics}


@app.get("/approvals/{approval_id}")
def get_approval(approval_id: str):
    approval = approval_store().get(approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")
    return approval


@app.get("/generated/{generated_id}")
def get_generated(generated_id: str):
    generated = generated_content_store().get(generated_id)
    if not generated:
        raise HTTPException(status_code=404, detail="Generated content not found")
    return generated


@app.get("/generated/{generated_id}/download")
def download_generated_file(generated_id: str):
    generated = generated_content_store().get(generated_id)
    if not generated or not generated.extra.get("pdf_path"):
        raise HTTPException(status_code=404, detail="No downloadable file for this item")
    return FileResponse(
        generated.extra["pdf_path"], filename=f"{generated.title or 'lead-magnet'}.pdf", media_type="application/pdf"
    )


@app.get("/generated/{generated_id}/image")
def get_generated_image(generated_id: str):
    generated = generated_content_store().get(generated_id)
    if not generated or not generated.extra.get("image_path"):
        raise HTTPException(status_code=404, detail="No image for this item")
    return FileResponse(generated.extra["image_path"], media_type="image/png")


@app.put("/generated/{generated_id}/schedule")
def schedule_generated(generated_id: str, payload: ScheduleRequest):
    generated = generated_content_store().get(generated_id)
    if not generated:
        raise HTTPException(status_code=404, detail="Generated content not found")

    generated.scheduled_channels = payload.channels
    generated.scheduled_at = payload.scheduled_at
    generated.schedule_error = None
    return generated_content_store().update(generated)


@app.post("/publish/{generated_id}")
def publish_endpoint(generated_id: str, payload: PublishRequest):
    generated = generated_content_store().get(generated_id)
    if not generated:
        raise HTTPException(status_code=404, detail="Generated content not found")

    if payload.channel == "wordpress":
        result = publish_to_wordpress(generated.title, generated.body, status="draft")
    elif payload.channel == "facebook":
        result = publish_to_facebook(generated.body)
    else:
        raise HTTPException(status_code=400, detail="channel must be 'facebook' or 'wordpress'")

    generated.status = "published"
    generated_content_store().update(generated)
    return {"generated_content_id": generated.id, "publish_result": result}


# --- Dashboard-facing API (same-machine, no auth required) -----------------


@app.get("/api/pending")
def api_pending():
    """Approvals still awaiting a human topic/format choice, newest first,
    with the source content's title attached for display."""
    pending = [a for a in approval_store().list() if a.status == "pending"]
    pending.sort(key=lambda a: a.created_at, reverse=True)

    results = []
    for approval in pending:
        raw_content = raw_content_store().get(approval.content_id)
        results.append(
            {
                "approval": approval,
                "content_title": raw_content.title if raw_content else "(source deleted)",
                "content_source_type": raw_content.source_type if raw_content else None,
            }
        )
    return results


@app.get("/api/generated")
def api_generated():
    """All generated drafts/published items, newest first."""
    items = generated_content_store().list()
    items.sort(key=lambda g: g.created_at, reverse=True)
    return items


@app.post("/api/generate")
def api_generate(payload: DashboardGenerateRequest):
    generated = approve_and_generate(
        payload.approval_id, payload.topic_id, payload.format_type, payload.custom_prompt
    )
    return generated


@app.get("/api/persona")
def api_get_persona():
    try:
        return load_persona()
    except FileNotFoundError:
        return Persona(persona_name="").model_dump()


@app.put("/api/persona")
def api_save_persona(payload: Persona):
    return save_persona(payload)


@app.get("/api/watch-config")
def api_get_watch_config():
    return load_watch_config()


@app.put("/api/watch-config")
def api_save_watch_config(payload: WatchConfigInput):
    config = load_watch_config()
    config.enabled = payload.enabled
    config.channel_url = payload.channel_url.strip()
    config.check_interval_hours = max(1, payload.check_interval_hours)
    return save_watch_config(config)


@app.post("/api/watch-config/check-now")
def api_check_watch_now():
    new_approval_ids = check_and_ingest_new_videos()
    return {"new_approval_ids": new_approval_ids}
