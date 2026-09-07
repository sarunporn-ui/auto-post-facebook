"""Meta Graph API client — publishes to a Page the user has connected via OAuth.

The Page id + access token come from the caller's `FacebookConnection` row
(decrypted just before the call), never from global env config.
"""
from __future__ import annotations
import requests

from src.config import get_settings


def publish_to_facebook(
    page_id: str,
    page_access_token: str,
    message: str,
    image_url: str | None = None,
) -> dict:
    settings = get_settings()
    base_url = f"https://graph.facebook.com/{settings.facebook_graph_api_version}/{page_id}"
    params = {"access_token": page_access_token}

    if image_url:
        response = requests.post(
            f"{base_url}/photos",
            params=params,
            data={"caption": message, "url": image_url},
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
