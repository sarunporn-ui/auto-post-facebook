"""Object storage for generated artifacts (images, PDFs).

Production: Supabase Storage (bucket = SUPABASE_STORAGE_BUCKET, public read).
Local dev: if Supabase isn't configured, `upload_bytes` returns None and callers
fall back to writing a local file under data/generated/.
"""
from __future__ import annotations
import logging
from functools import lru_cache

from src.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def _client():
    settings = get_settings()
    if not (settings.supabase_url and settings.supabase_service_role_key):
        return None
    try:
        from supabase import create_client

        return create_client(settings.supabase_url, settings.supabase_service_role_key)
    except Exception:
        logger.exception("Could not create Supabase client")
        return None


def is_enabled() -> bool:
    return _client() is not None


def upload_bytes(object_path: str, data: bytes, content_type: str) -> str | None:
    """Upload to `<bucket>/<object_path>`; return a public URL, or None if
    object storage isn't configured (caller should then keep a local file)."""
    client = _client()
    if client is None:
        return None

    settings = get_settings()
    bucket = client.storage.from_(settings.supabase_storage_bucket)
    try:
        bucket.upload(
            object_path,
            data,
            {"content-type": content_type, "upsert": "true"},
        )
        return bucket.get_public_url(object_path)
    except Exception:
        logger.exception("Supabase Storage upload failed for %s", object_path)
        return None
