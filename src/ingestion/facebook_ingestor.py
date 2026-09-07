"""Ingests Facebook content: either a public post URL (best-effort scrape of
Open Graph metadata — Facebook does not allow scraping full post bodies
without the Graph API/login) or raw pasted text.
"""
from __future__ import annotations
import requests
from bs4 import BeautifulSoup

from src.models import RawContent

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ContentOS/1.0)"}


def _looks_like_url(value: str) -> bool:
    return value.strip().lower().startswith(("http://", "https://"))


def _scrape_og_tags(url: str) -> tuple[str, str]:
    response = requests.get(url, headers=_HEADERS, timeout=15)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    def og(prop: str) -> str:
        tag = soup.find("meta", property=prop)
        return tag["content"] if tag and tag.has_attr("content") else ""

    return og("og:title"), og("og:description")


def ingest_facebook(url_or_text: str) -> RawContent:
    """If given a URL, scrape publicly available OG metadata. Otherwise treat
    the input as already-extracted post text (recommended for private/owned
    pages, since Facebook restricts scraping of full post bodies)."""
    if _looks_like_url(url_or_text):
        title, description = _scrape_og_tags(url_or_text)
        if not description:
            raise ValueError(
                "Could not extract post text from the Facebook URL (page may "
                "require login). Paste the post text directly instead."
            )
        return RawContent(
            source_type="facebook",
            source_url=url_or_text,
            title=title or "Facebook post",
            raw_text=description,
        )

    return RawContent(
        source_type="facebook",
        source_url=None,
        title="Facebook post (pasted text)",
        raw_text=url_or_text,
    )
