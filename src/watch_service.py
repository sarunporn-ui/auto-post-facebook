"""YouTube channel auto-fetch: periodically checks a configured channel for new
videos and automatically ingests + analyzes any not seen before, so new ideas
show up in the dashboard's Pending list without the user pasting a link."""
from __future__ import annotations
import json
import logging
import time

from src.config import get_settings
from src.models import WatchConfig, ApprovalRequest
from src.stores import raw_content_store, approval_store
from src.ai_brain.brain import analyze_content
from src.ai_brain.persona import load_persona
from src.ingestion.youtube_ingestor import ingest_youtube

logger = logging.getLogger(__name__)


def _watch_config_path():
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings.data_dir / "watch_config.json"


def load_watch_config() -> WatchConfig:
    path = _watch_config_path()
    if not path.exists():
        return WatchConfig()
    return WatchConfig.model_validate(json.loads(path.read_text() or "{}"))


def save_watch_config(config: WatchConfig) -> WatchConfig:
    _watch_config_path().write_text(config.model_dump_json(indent=2))
    return config


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


def check_and_ingest_new_videos() -> list[str]:
    """Check the configured channel for videos not yet seen, ingest + analyze
    each one, and return the list of newly created approval IDs."""
    config = load_watch_config()
    if not config.enabled or not config.channel_url:
        return []

    seen = set(config.seen_video_ids)
    new_approval_ids: list[str] = []

    try:
        videos = list_channel_videos(config.channel_url)
    except Exception:
        logger.exception("Failed to list videos for channel %s", config.channel_url)
        config.last_checked_at = time.time()
        save_watch_config(config)
        return []

    persona = load_persona()
    for video in videos:
        video_id = video["video_id"]
        if video_id in seen:
            continue
        seen.add(video_id)
        try:
            raw_content = ingest_youtube(video["url"])
            raw_content_store().save(raw_content)
            _, topics = analyze_content(raw_content, persona)
            if topics:
                approval = ApprovalRequest(content_id=raw_content.id, topics=topics)
                approval_store().save(approval)
                new_approval_ids.append(approval.id)
        except Exception:
            logger.exception("Failed to auto-ingest video %s", video_id)

    config.seen_video_ids = list(seen)[-500:]  # cap unbounded growth
    config.last_checked_at = time.time()
    save_watch_config(config)
    return new_approval_ids
