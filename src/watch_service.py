"""YouTube channel auto-fetch: per user, periodically checks a configured channel
for new videos and automatically ingests + analyzes any not seen before, so new
ideas show up in the dashboard's Pending list without pasting a link."""
from __future__ import annotations
import logging
import time

from sqlmodel import Session

from src.models import ApprovalRequest
from src.repositories import (
    approval_repo,
    get_or_create_watch_config,
    raw_content_repo,
)
from src.ai_brain.brain import analyze_content
from src.ai_brain.persona import load_persona
from src.ingestion.youtube_ingestor import ingest_youtube

logger = logging.getLogger(__name__)


def list_channel_videos(channel_url: str, limit: int = 15) -> list[dict]:
    """List recent videos on a channel without downloading them (flat extraction)."""
    import yt_dlp

    url = channel_url.strip().rstrip("/")
    if "/videos" not in url:
        url = f"{url}/videos"

    ydl_opts = {"extract_flat": True, "playlistend": limit, "quiet": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    entries = (info or {}).get("entries", []) or []
    videos = []
    for entry in entries:
        video_id = entry.get("id")
        if not video_id:
            continue
        videos.append(
            {
                "video_id": video_id,
                "url": entry.get("url") or f"https://www.youtube.com/watch?v={video_id}",
                "title": entry.get("title", ""),
            }
        )
    return videos


def check_and_ingest_new_videos(session: Session, user_id: str) -> list[str]:
    """For one user: check their configured channel for videos not yet seen,
    ingest + analyze each, return the list of newly created approval IDs."""
    config = get_or_create_watch_config(session, user_id)
    if not config.enabled or not config.channel_url:
        return []

    seen = set(config.seen_video_ids or [])
    new_approval_ids: list[str] = []

    try:
        videos = list_channel_videos(config.channel_url)
    except Exception:
        logger.exception("Failed to list videos for channel %s", config.channel_url)
        config.last_checked_at = time.time()
        session.add(config)
        session.commit()
        return []

    persona = load_persona(session, user_id)
    for video in videos:
        video_id = video["video_id"]
        if video_id in seen:
            continue
        seen.add(video_id)
        try:
            raw_content = ingest_youtube(video["url"])
            raw_content.user_id = user_id
            raw_content_repo.add(session, raw_content)
            _, topics = analyze_content(raw_content, persona)
            if topics:
                approval = ApprovalRequest(
                    user_id=user_id,
                    content_id=raw_content.id,
                    topics=[t.model_dump() for t in topics],
                )
                approval_repo.add(session, approval)
                new_approval_ids.append(approval.id)
        except Exception:
            logger.exception("Failed to auto-ingest video %s", video_id)

    config.seen_video_ids = list(seen)[-500:]  # cap unbounded growth
    config.last_checked_at = time.time()
    session.add(config)
    session.commit()
    return new_approval_ids
