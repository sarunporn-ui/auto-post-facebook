"""Extracts transcripts from YouTube videos.

Primary path: `youtube-transcript-api` (fast, free, works whenever captions —
manual or auto-generated — exist). Fallback: download audio with `yt-dlp` and
transcribe via the OpenAI Whisper API, for videos with no captions at all.
"""
from __future__ import annotations
import re
import tempfile
from pathlib import Path

from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound

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


def _fetch_via_captions(video_id: str) -> str:
    transcript = YouTubeTranscriptApi().fetch(video_id)
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
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        with open(audio_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model=settings.whisper_model, file=audio_file
            )
        return transcription.text


def ingest_youtube(url: str) -> RawContent:
    video_id = extract_video_id(url)
    try:
        text = _fetch_via_captions(video_id)
        method = "captions"
    except (TranscriptsDisabled, NoTranscriptFound):
        text = _fetch_via_whisper(url)
        method = "whisper"
    except Exception as exc:
        # Any other caption failure (YouTube blocking a datacenter IP, transient
        # 429, parser change) — try the audio+Whisper path, then give up with a
        # clear message rather than a bare 500.
        try:
            text = _fetch_via_whisper(url)
            method = "whisper"
        except Exception as exc2:
            raise RuntimeError(
                "Could not get this video's transcript. YouTube may be blocking "
                f"requests from the server, or the video has no captions. "
                f"({type(exc).__name__}: {exc}; whisper: {type(exc2).__name__}: {exc2})"
            ) from exc2

    return RawContent(
        source_type="youtube",
        source_url=url,
        title=f"YouTube video {video_id}",
        raw_text=text,
        meta={"video_id": video_id, "transcript_method": method},
    )
