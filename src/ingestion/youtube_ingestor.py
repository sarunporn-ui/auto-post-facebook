"""Extracts transcripts from YouTube videos.

Cloud hosts (Railway, AWS, GCP, ...) all get IP-blocked by YouTube directly —
it's blocked by IP range (ASN), not by hostname or account, so this hits any
cloud provider identically. Local dev on a home IP is unaffected.

Path order:
  1. Supadata (hosted transcript API — sidesteps the block entirely; used
     whenever SUPADATA_API_KEY is set, i.e. in production)
  2. `youtube-transcript-api` direct (fast, free, works fine from a home IP —
     this is what local dev actually uses)
  3. yt-dlp + OpenAI Whisper (audio download + transcribe — last resort for
     videos with no captions at all; heavier, so kept as final fallback)
"""
from __future__ import annotations
import re
import tempfile
from pathlib import Path

import requests
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from youtube_transcript_api.proxies import WebshareProxyConfig

from src.models import RawContent
from src.config import get_settings

_YOUTUBE_ID_RE = re.compile(
    r"(?:youtu\.be/|youtube\.com/(?:watch\?v=|shorts/|embed/))([A-Za-z0-9_-]{11})"
)


def extract_video_id(url: str) -> str:
    match = _YOUTUBE_ID_RE.search(url)
    if not match:
        raise ValueError(f"Could not parse a YouTube video ID from: {url}")
    return match.group(1)


def _proxy_url() -> str | None:
    """http://user:pass@p.webshare.io:80 if Webshare creds are set, else None.

    Cloud hosts (Railway, AWS, ...) get IP-blocked by YouTube directly — a home
    IP doesn't need this, so it's a no-op in local dev where these are unset."""
    s = get_settings()
    if s.webshare_proxy_username and s.webshare_proxy_password:
        return f"http://{s.webshare_proxy_username}:{s.webshare_proxy_password}@p.webshare.io:80"
    return None


class _SupadataUnavailable(Exception):
    """This video has no transcript on Supadata's side — not a config/quota
    problem, so callers should fall through to the direct path instead of
    treating it as a hard failure."""


def _fetch_via_supadata(video_id: str) -> str:
    """docs.supadata.ai/youtube/get-transcript — hosted transcript API, billed
    per video regardless of the caller's IP, so it isn't affected by YouTube's
    cloud-IP block."""
    settings = get_settings()
    resp = requests.get(
        "https://api.supadata.ai/v1/youtube/transcript",
        headers={"x-api-key": settings.supadata_api_key},
        params={"videoId": video_id, "text": "true"},
        timeout=30,
    )
    if resp.status_code == 200:
        content = resp.json().get("content", "")
        if not content:
            raise _SupadataUnavailable(f"Supadata returned an empty transcript for {video_id}")
        return content
    if resp.status_code == 206:
        raise _SupadataUnavailable(f"No transcript available for {video_id} (Supadata)")
    resp.raise_for_status()
    raise RuntimeError(f"Unexpected Supadata response {resp.status_code}: {resp.text[:300]}")


def _fetch_via_captions(video_id: str) -> str:
    s = get_settings()
    proxy_config = None
    if s.webshare_proxy_username and s.webshare_proxy_password:
        proxy_config = WebshareProxyConfig(
            proxy_username=s.webshare_proxy_username,
            proxy_password=s.webshare_proxy_password,
        )
    transcript = YouTubeTranscriptApi(proxy_config=proxy_config).fetch(video_id)
    return " ".join(snippet.text for snippet in transcript)


def _fetch_via_whisper(url: str) -> str:
    """Fallback for videos without captions: download audio, transcribe with Whisper.

    Requires `yt-dlp` + a local ffmpeg install, and OPENAI_API_KEY to be set
    regardless of which LLM_PROVIDER is used for the rest of the pipeline.
    """
    import yt_dlp
    from openai import OpenAI

    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)

    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = Path(tmpdir) / "audio.mp3"
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": str(audio_path.with_suffix("")),
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}],
            "quiet": True,
        }
        proxy = _proxy_url()
        if proxy:
            ydl_opts["proxy"] = proxy
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        with open(audio_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model=settings.whisper_model, file=audio_file
            )
        return transcription.text


def ingest_youtube(url: str) -> RawContent:
    video_id = extract_video_id(url)
    settings = get_settings()
    errors: list[str] = []

    if settings.supadata_api_key:
        try:
            text = _fetch_via_supadata(video_id)
            return RawContent(
                source_type="youtube",
                source_url=url,
                title=f"YouTube video {video_id}",
                raw_text=text,
                meta={"video_id": video_id, "transcript_method": "supadata"},
            )
        except _SupadataUnavailable as exc:
            errors.append(f"supadata: {exc}")  # no transcript there either — try direct/whisper
        except Exception as exc:
            errors.append(f"supadata: {type(exc).__name__}: {exc}")  # quota/network — fall through

    try:
        text = _fetch_via_captions(video_id)
        method = "captions"
    except (TranscriptsDisabled, NoTranscriptFound) as exc:
        errors.append(f"captions: {type(exc).__name__}: {exc}")
        try:
            text = _fetch_via_whisper(url)
            method = "whisper"
        except Exception as exc2:
            errors.append(f"whisper: {type(exc2).__name__}: {exc2}")
            raise RuntimeError(
                "Could not get this video's transcript — no captions, and the "
                f"audio fallback failed too. ({'; '.join(errors)})"
            ) from exc2
    except Exception as exc:
        # Any other caption failure (YouTube blocking a datacenter IP, transient
        # 429, parser change) — try the audio+Whisper path, then give up with a
        # clear message rather than a bare 500.
        errors.append(f"captions: {type(exc).__name__}: {exc}")
        try:
            text = _fetch_via_whisper(url)
            method = "whisper"
        except Exception as exc2:
            errors.append(f"whisper: {type(exc2).__name__}: {exc2}")
            raise RuntimeError(
                "Could not get this video's transcript. YouTube may be blocking "
                f"requests from the server, or the video has no captions. ({'; '.join(errors)})"
            ) from exc2

    return RawContent(
        source_type="youtube",
        source_url=url,
        title=f"YouTube video {video_id}",
        raw_text=text,
        meta={"video_id": video_id, "transcript_method": method},
    )
