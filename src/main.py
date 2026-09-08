"""FastAPI application: ingestion -> AI analysis -> human approval ->
multi-format generation -> publishing, multi-user.

Run:  uvicorn src.main:app --reload
Dashboard:  http://localhost:8000/dashboard
"""
from __future__ import annotations
import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlmodel import Session

from src.auth import get_current_user
from src.config import get_settings
from src.crypto import decrypt
from src.db import get_session, init_db, session_scope
from src.models import (
    ApprovalRequest,
    GeneratedContent,
    PersonaData,
    User,
)
from src.repositories import (
    approval_repo,
    generated_repo,
    get_facebook_connection,
    get_or_create_watch_config,
    get_wordpress_connection,
    list_all_due_generated,
    list_all_enabled_watch_configs,
    raw_content_repo,
)
from src.ingestion.youtube_ingestor import ingest_youtube
from src.ingestion.facebook_ingestor import ingest_facebook
from src.ai_brain.brain import analyze_content
from src.ai_brain.persona import load_persona, save_persona
from src.approval.webhook import router as approval_router
from src.approval.service import approve_and_generate
from src.facebook.oauth import router as facebook_router
from src.publisher.facebook_publisher import publish_to_facebook
from src.publisher.wordpress_publisher import publish_to_wordpress
from src.watch_service import check_and_ingest_new_videos

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
logger = logging.getLogger(__name__)


# --- Publishing (shared by the /publish endpoint and the scheduler) --------


def _publish_one(session: Session, generated: GeneratedContent, channels: list[str]) -> list[str]:
    """Publish `generated` to each channel; return a list of per-channel errors."""
    errors: list[str] = []
    for channel in channels:
        try:
            if channel == "facebook":
                conn = get_facebook_connection(session, generated.user_id)
                if not conn:
                    raise RuntimeError("Facebook Page not connected")
                publish_to_facebook(
                    conn.page_id,
                    decrypt(conn.encrypted_page_token),
                    generated.body,
                    generated.extra.get("image_url"),
                )
            elif channel == "wordpress":
                conn = get_wordpress_connection(session, generated.user_id)
                if not conn:
                    raise RuntimeError("WordPress site not connected")
                publish_to_wordpress(
                    conn.site_url,
                    conn.username,
                    decrypt(conn.encrypted_app_password),
                    generated.title,
                    generated.body,
                    status="draft",
                )
            else:
                raise RuntimeError(f"unknown channel '{channel}'")
        except Exception as exc:  # noqa: BLE001 - recorded on the item, not raised
            errors.append(f"{channel}: {exc}")
    return errors


def _publish_due_scheduled_items(session: Session) -> int:
    now = time.time()
    due = list_all_due_generated(session, now)
    for generated in due:
        errors = _publish_one(session, generated, generated.scheduled_channels or [])
        if errors:
            generated.schedule_error = "; ".join(errors)
            generated.scheduled_at = None
        else:
            generated.status = "published"
            generated.schedule_error = None
            generated.scheduled_at = None
            generated.scheduled_channels = []
        session.add(generated)
    session.commit()
    return len(due)


def _run_due_watch_checks(session: Session) -> int:
    checked = 0
    for cfg in list_all_enabled_watch_configs(session):
        due = cfg.last_checked_at is None or (
            time.time() - cfg.last_checked_at >= cfg.check_interval_hours * 3600
        )
        if due:
            try:
                check_and_ingest_new_videos(session, cfg.user_id)
                checked += 1
            except Exception:
                logger.exception("watch check failed for user %s", cfg.user_id)
    return checked


# --- Background loops -----------------------------------------------------

_SCHEDULE_POLL_SECONDS = 60
_WATCH_POLL_SECONDS = 300


async def _schedule_loop() -> None:
    while True:
        try:
            with session_scope() as session:
                await asyncio.to_thread(_publish_due_scheduled_items, session)
        except Exception:
            logger.exception("Schedule loop iteration failed")
        await asyncio.sleep(_SCHEDULE_POLL_SECONDS)


async def _watch_loop() -> None:
    while True:
        try:
            with session_scope() as session:
                await asyncio.to_thread(_run_due_watch_checks, session)
        except Exception:
            logger.exception("Channel watch loop iteration failed")
        await asyncio.sleep(_WATCH_POLL_SECONDS)


_STARTUP_DB_ERROR: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _STARTUP_DB_ERROR
    try:
        init_db()
        _STARTUP_DB_ERROR = None
    except Exception as exc:  # keep serving so /healthz can report the cause
        _STARTUP_DB_ERROR = f"{type(exc).__name__}: {exc}"
        logger.exception("init_db() failed at startup — DB is unreachable")
    watch_task = asyncio.create_task(_watch_loop())
    schedule_task = asyncio.create_task(_schedule_loop())
    yield
    watch_task.cancel()
    schedule_task.cancel()


app = FastAPI(title="Automated Content OS", version="0.2.0", lifespan=lifespan)
app.include_router(approval_router)
app.include_router(facebook_router)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


# --- Request bodies ------------------------------------------------------


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


# --- Public routes -----------------------------------------------------


@app.get("/")
def root():
    return {"status": "ok", "service": "Automated Content OS", "dashboard": "/dashboard"}


@app.get("/healthz")
def healthz():
    """Reports whether the DB is reachable. Returns 200 even when it is not, so
    the failure cause is visible without digging through container logs."""
    from sqlalchemy import text

    from src.db import engine

    db_ok, db_error = True, None
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        db_ok = False
        db_error = f"{type(exc).__name__}: {exc}"

    s = get_settings()
    return {
        "ok": db_ok,
        "db": "ok" if db_ok else "error",
        "db_error": db_error,
        "startup_db_error": _STARTUP_DB_ERROR,
        "auth_enabled": bool(s.supabase_url and s.supabase_anon_key),
        # Booleans only — never the values — so "did the env var actually land
        # on this deploy" can be checked without digging through logs or
        # exposing a secret. Add a flag here whenever a new integration key
        # is introduced.
        "integrations": {
            "supadata": bool(s.supadata_api_key),
            "webshare_proxy": bool(s.webshare_proxy_username and s.webshare_proxy_password),
            "facebook": bool(s.facebook_app_id and s.facebook_app_secret),
        },
    }


@app.get("/dashboard")
def dashboard():
    return FileResponse(WEB_DIR / "index.html")


_LEGAL_PAGE = """<!doctype html><meta charset="utf-8"><title>{title}</title>
<body style="font-family:system-ui;max-width:640px;margin:60px auto;padding:0 20px;line-height:1.6">
<h1>{title}</h1>{body}</body>"""


@app.get("/privacy", response_class=HTMLResponse)
def privacy():
    return _LEGAL_PAGE.format(
        title="นโยบายความเป็นส่วนตัว — Content OS",
        body="""
<p>Content OS ช่วยผู้ใช้ร่างคอนเทนต์และเผยแพร่ไปยังเพจ Facebook ที่ผู้ใช้เชื่อมต่อเอง</p>
<h3>ข้อมูลที่เราเก็บ</h3>
<ul>
<li>บัญชีของคุณ: อีเมล/ตัวระบุจากผู้ให้บริการล็อกอิน (Supabase Auth)</li>
<li>คอนเทนต์ที่คุณสร้าง: ข้อความต้นทางที่นำเข้า, ฉบับร่างที่สร้าง, การตั้งค่ากลุ่มเป้าหมาย</li>
<li>โทเคนเข้าถึงเพจ Facebook ของเพจที่คุณเลือกเชื่อม — เก็บแบบเข้ารหัส ใช้เพื่อเผยแพร่โพสต์
ที่คุณตั้งเวลาไว้เท่านั้น ยกเลิกได้ตลอดด้วยปุ่ม "ยกเลิกการเชื่อม"</li>
</ul>
<h3>สิ่งที่เราไม่ทำ</h3>
<p>เราไม่ขายข้อมูล และไม่โพสต์อะไรที่คุณไม่ได้สร้างและตั้งเวลาไว้</p>
<h3>การลบข้อมูล</h3>
<p>การยกเลิกการเชื่อมเพจจะลบโทเคนทันที หากต้องการลบบัญชีและข้อมูลทั้งหมด
ติดต่อผู้ดูแลระบบนี้ ดูเพิ่มที่ /data-deletion</p>
<p style="color:#888;font-size:13px">English summary: Content OS stores your account email, the content
you create, and an encrypted Facebook Page token used only to publish posts you schedule.
We do not sell data. Disconnecting a Page deletes its token; contact the operator to delete your account.</p>
""",
    )


@app.get("/data-deletion", response_class=HTMLResponse)
def data_deletion():
    return _LEGAL_PAGE.format(
        title="การลบข้อมูล — Content OS",
        body="<p>วิธีลบข้อมูลของคุณ: เปิดแดชบอร์ด กดปุ่ม <b>ยกเลิกการเชื่อม</b> บนการ์ดเพจ "
        "Facebook (จะลบโทเคนที่เก็บไว้) จากนั้นแจ้งผู้ดูแลระบบนี้เพื่อลบบัญชี ข้อมูลทุกแถวของคุณ "
        "ผูกกับ user id เดียวและถูกลบพร้อมกัน</p>"
        "<p style='color:#888;font-size:13px'>English: to delete your data, click "
        "<b>Disconnect</b> on the Facebook Page card, then ask the operator to delete your account.</p>",
    )


@app.get("/api/config")
def api_config():
    """Public — tells the frontend whether to show the login gate and which
    Supabase project to authenticate against."""
    settings = get_settings()
    auth_enabled = bool(settings.supabase_url and settings.supabase_anon_key)
    return {
        "auth_enabled": auth_enabled,
        "supabase_url": settings.supabase_url if auth_enabled else None,
        "supabase_anon_key": settings.supabase_anon_key if auth_enabled else None,
    }


@app.get("/api/me")
def api_me(current_user: User = Depends(get_current_user)):
    return {"id": current_user.id, "email": current_user.email}


# --- Ingestion ---------------------------------------------------------


@app.post("/ingest/youtube")
def ingest_youtube_endpoint(
    payload: YoutubeIngestRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    try:
        raw_content = ingest_youtube(payload.url)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("YouTube ingest failed for %s", payload.url)
        raise HTTPException(status_code=502, detail=f"ดึงเนื้อหา YouTube ไม่สำเร็จ: {exc}")
    raw_content.user_id = current_user.id
    return raw_content_repo.add(session, raw_content)


@app.post("/ingest/facebook")
def ingest_facebook_endpoint(
    payload: FacebookIngestRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    try:
        raw_content = ingest_facebook(payload.url_or_text)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Facebook ingest failed")
        raise HTTPException(status_code=502, detail=f"อ่านเนื้อหาไม่สำเร็จ: {exc}")
    raw_content.user_id = current_user.id
    return raw_content_repo.add(session, raw_content)


@app.post("/analyze/{content_id}")
def analyze_endpoint(
    content_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    raw_content = raw_content_repo.get(session, current_user.id, content_id)
    if not raw_content:
        raise HTTPException(status_code=404, detail="Raw content not found")

    persona = load_persona(session, current_user.id)
    try:
        takeaways, topics = analyze_content(raw_content, persona)
    except Exception as exc:
        logger.exception("analyze_content failed for %s", content_id)
        raise HTTPException(status_code=502, detail=f"AI วิเคราะห์ไม่สำเร็จ: {exc}")
    if not topics:
        raise HTTPException(status_code=502, detail="AI Brain returned no topics")

    approval = ApprovalRequest(
        user_id=current_user.id,
        content_id=content_id,
        topics=[t.model_dump() for t in topics],
    )
    approval_repo.add(session, approval)
    return {"approval_id": approval.id, "core_takeaways": takeaways, "topics": topics}


@app.get("/approvals/{approval_id}")
def get_approval(
    approval_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    approval = approval_repo.get(session, current_user.id, approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")
    return approval


# --- Generated content ------------------------------------------------


@app.get("/generated/{generated_id}")
def get_generated(
    generated_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    generated = generated_repo.get(session, current_user.id, generated_id)
    if not generated:
        raise HTTPException(status_code=404, detail="Generated content not found")
    return generated


@app.get("/generated/{generated_id}/download")
def download_generated_file(
    generated_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    generated = generated_repo.get(session, current_user.id, generated_id)
    if not generated:
        raise HTTPException(status_code=404, detail="Generated content not found")
    if generated.extra.get("pdf_url"):
        return RedirectResponse(generated.extra["pdf_url"])
    if generated.extra.get("pdf_path"):
        return FileResponse(
            generated.extra["pdf_path"],
            filename=f"{generated.title or 'lead-magnet'}.pdf",
            media_type="application/pdf",
        )
    raise HTTPException(status_code=404, detail="No downloadable file for this item")


@app.get("/generated/{generated_id}/image")
def get_generated_image(
    generated_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    generated = generated_repo.get(session, current_user.id, generated_id)
    if not generated:
        raise HTTPException(status_code=404, detail="Generated content not found")
    if generated.extra.get("image_url"):
        return RedirectResponse(generated.extra["image_url"])
    if generated.extra.get("image_path"):
        return FileResponse(generated.extra["image_path"], media_type="image/png")
    raise HTTPException(status_code=404, detail="No image for this item")


@app.put("/generated/{generated_id}/schedule")
def schedule_generated(
    generated_id: str,
    payload: ScheduleRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    generated = generated_repo.get(session, current_user.id, generated_id)
    if not generated:
        raise HTTPException(status_code=404, detail="Generated content not found")
    generated.scheduled_channels = payload.channels
    generated.scheduled_at = payload.scheduled_at
    generated.schedule_error = None
    return generated_repo.update(session, generated)


@app.post("/publish/{generated_id}")
def publish_endpoint(
    generated_id: str,
    payload: PublishRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    generated = generated_repo.get(session, current_user.id, generated_id)
    if not generated:
        raise HTTPException(status_code=404, detail="Generated content not found")
    if payload.channel not in ("facebook", "wordpress"):
        raise HTTPException(status_code=400, detail="channel must be 'facebook' or 'wordpress'")

    errors = _publish_one(session, generated, [payload.channel])
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    generated.status = "published"
    generated_repo.update(session, generated)
    return {"generated_content_id": generated.id, "status": "published"}


# --- Dashboard API --------------------------------------------------


@app.get("/api/pending")
def api_pending(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    pending = [a for a in approval_repo.list(session, current_user.id) if a.status == "pending"]
    pending.sort(key=lambda a: a.created_at, reverse=True)

    results = []
    for approval in pending:
        raw_content = raw_content_repo.get(session, current_user.id, approval.content_id)
        results.append(
            {
                "approval": approval,
                "content_title": raw_content.title if raw_content else "(source deleted)",
                "content_source_type": raw_content.source_type if raw_content else None,
            }
        )
    return results


@app.get("/api/generated")
def api_generated(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    items = generated_repo.list(session, current_user.id)
    items.sort(key=lambda g: g.created_at, reverse=True)
    return items


@app.post("/api/generate")
def api_generate(
    payload: DashboardGenerateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    return approve_and_generate(
        session,
        current_user.id,
        payload.approval_id,
        payload.topic_id,
        payload.format_type,
        payload.custom_prompt,
    )


@app.get("/api/persona")
def api_get_persona(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    return load_persona(session, current_user.id)


@app.put("/api/persona")
def api_save_persona(
    payload: PersonaData,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    return save_persona(session, current_user.id, payload)


@app.get("/api/watch-config")
def api_get_watch_config(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    return get_or_create_watch_config(session, current_user.id)


@app.put("/api/watch-config")
def api_save_watch_config(
    payload: WatchConfigInput,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    cfg = get_or_create_watch_config(session, current_user.id)
    cfg.enabled = payload.enabled
    cfg.channel_url = payload.channel_url.strip()
    cfg.check_interval_hours = max(1, payload.check_interval_hours)
    session.add(cfg)
    session.commit()
    session.refresh(cfg)
    return cfg


@app.post("/api/watch-config/check-now")
def api_check_watch_now(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    new_approval_ids = check_and_ingest_new_videos(session, current_user.id)
    return {"new_approval_ids": new_approval_ids}


# --- Internal cron (backup trigger for hosts that sleep) ------------


@app.post("/internal/cron/tick")
def internal_cron_tick(x_cron_secret: str | None = Header(default=None)):
    settings = get_settings()
    if x_cron_secret != settings.internal_cron_secret:
        raise HTTPException(status_code=401, detail="bad cron secret")
    with session_scope() as session:
        published = _publish_due_scheduled_items(session)
    with session_scope() as session:
        watched = _run_due_watch_checks(session)
    return {"published": published, "watch_checks": watched}
