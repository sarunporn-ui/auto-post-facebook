"""Centralized application configuration loaded from environment variables (.env)."""
from pathlib import Path
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- LLM Providers ---
    llm_provider: str = "openai"  # openai | anthropic | gemini
    llm_model: str = "gpt-4o"
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None

    # --- Ingestion ---
    whisper_model: str = "whisper-1"

    # --- Telegram ---
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None

    # --- Approval webhook (dashboard/API alternative to Telegram) ---
    approval_webhook_secret: str = "change-me"

    # --- Meta / Facebook Graph API ---
    meta_page_id: Optional[str] = None
    meta_page_access_token: Optional[str] = None
    meta_graph_api_version: str = "v19.0"

    # --- WordPress ---
    wordpress_url: Optional[str] = None  # e.g. https://example.com
    wordpress_username: Optional[str] = None
    wordpress_app_password: Optional[str] = None

    # --- App ---
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    data_dir: Path = BASE_DIR / "data"
    persona_file: Path = BASE_DIR / "target_persona.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()
