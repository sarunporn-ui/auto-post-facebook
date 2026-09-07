"""Symmetric encryption for secrets stored at rest (Facebook Page tokens,
WordPress application passwords).

`FERNET_KEY` must be a urlsafe-base64 32-byte key — generate one with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

In local dev, if `FERNET_KEY` is unset a deterministic key derived from a fixed
dev seed is used so the app still runs (NOT for production).
"""
from __future__ import annotations
import base64
import hashlib

from cryptography.fernet import Fernet

from src.config import get_settings


def _get_fernet() -> Fernet:
    settings = get_settings()
    key = settings.fernet_key
    if not key:
        # Dev-only fallback: stable key so encrypt/decrypt round-trips across restarts.
        digest = hashlib.sha256(b"content-os-dev-fernet-seed").digest()
        key = base64.urlsafe_b64encode(digest).decode()
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)


def encrypt(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    return _get_fernet().decrypt(token.encode()).decode()
