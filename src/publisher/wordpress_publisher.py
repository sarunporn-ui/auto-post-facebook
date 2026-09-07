"""WordPress REST API client — publishes long-form content to a user's site.

Credentials come from the caller's `WordPressConnection` row (decrypted just
before the call), never from global env config.
"""
from __future__ import annotations
import requests


def publish_to_wordpress(
    site_url: str,
    username: str,
    app_password: str,
    title: str,
    content_markdown: str,
    status: str = "draft",
) -> dict:
    import markdown

    content_html = markdown.markdown(content_markdown, extensions=["extra"])

    endpoint = f"{site_url.rstrip('/')}/wp-json/wp/v2/posts"
    response = requests.post(
        endpoint,
        auth=(username, app_password),
        json={"title": title, "content": content_html, "status": status},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()
