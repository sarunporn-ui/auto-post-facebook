"""Meta Graph API client for publishing approved content to a Facebook Page."""
from __future__ import annotations
import requests

from src.config import get_settings


def publish_to_facebook(message: str, image_path: str | None = None) -> dict:
    settings = get_settings()
    if not settings.meta_page_id or not settings.meta_page_access_token:
        raise RuntimeError("META_PAGE_ID / META_PAGE_ACCESS_TOKEN are not configured.")

    base_url = f"https://graph.facebook.com/{settings.meta_graph_api_version}/{settings.meta_page_id}"
    params = {"access_token": settings.meta_page_access_token}

    if image_path:
        with open(image_path, "rb") as image_file:
            response = requests.post(
                f"{base_url}/photos",
                params=params,
                data={"caption": message},
                files={"source": image_file},
                timeout=30,
            )
    else:
        response = requests.post(
            f"{base_url}/feed",
            params=params,
            data={"message": message},
            timeout=30,
        )

    response.raise_for_status()
    return response.json()
