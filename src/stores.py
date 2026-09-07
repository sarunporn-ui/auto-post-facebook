"""Singleton JSON-backed stores for each entity type."""
from functools import lru_cache

from src.storage import JsonStore
from src.models import RawContent, ApprovalRequest, GeneratedContent


@lru_cache
def raw_content_store() -> JsonStore:
    return JsonStore("raw_content", RawContent)


@lru_cache
def approval_store() -> JsonStore:
    return JsonStore("approvals", ApprovalRequest)


@lru_cache
def generated_content_store() -> JsonStore:
    return JsonStore("generated_content", GeneratedContent)
