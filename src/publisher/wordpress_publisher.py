"""WordPress REST API client for publishing long-form content to a website."""
from __future__ import annotations
import requests

from src.config import get_settings


def publish_to_wordpress(title: str, content_markdown: str, status: str = "draft") -> dict:
    settings = get_settings()
    if not (settings.wordpress_url and settings.wordpress_username and settings.wordpress_app_password):
        raise RuntimeError(
            "WORDPRESS_URL / WORDPRESS_USERNAME / WORDPRESS_APP_PASSWORD are not configured."
        )

    import markdown

    content_html = markdown.markdown(content_markdown, extensions=["extra"])

    endpoint = f"{settings.wordpress_url.rstrip('/')}/wp-json/wp/v2/posts"
    response = requests.post(
        endpoint,
        auth=(settings.wordpress_username, settings.wordpress_app_password),
        json={"title": title, "content": content_html, "status": status},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()
