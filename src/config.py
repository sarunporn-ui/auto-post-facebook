"""Centralized application configuration loaded from environment variables (.env)."""
from pathlib import Path
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # env_file ต้องเป็น absolute path — ไม่งั้นเวลารันจากโฟลเดอร์อื่น (หรือใน container)
    # pydantic จะหา .env ไม่เจอแล้วเงียบ ๆ ใช้ค่า default ทั้งหมดโดยไม่แจ้ง error
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    # --- LLM Providers ---
    llm_provider: str = "openai"  # openai | anthropic | gemini
    llm_model: str = "gpt-4o"
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None

    # --- Ingestion ---
    whisper_model: str = "whisper-1"

    # --- Webshare proxy (datacenter tier tested 2026-09-08: still IP-blocked by
    # YouTube — kept here in case a residential tier is purchased later, but not
    # the active path. See supadata_api_key below.) ---
    webshare_proxy_username: Optional[str] = None
    webshare_proxy_password: Optional[str] = None

    # --- Supadata (hosted YouTube transcript API — sidesteps IP blocking
    # entirely; free tier = 100 credits/month, no card. docs.supadata.ai) ---
    # Unset locally — falls back to the direct youtube-transcript-api path,
    # which already works fine from a home IP.
    supadata_api_key: Optional[str] = None

    # --- Database ---
    # local default = sqlite file; production = Supabase Postgres pooler URL,
    # e.g. postgresql+psycopg://postgres.<ref>:<pw>@<host>:6543/postgres?sslmode=require
    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'content_os.db'}"

    # --- Supabase (Auth JWT verification + Storage) ---
    supabase_url: Optional[str] = None
    supabase_anon_key: Optional[str] = None
    supabase_service_role_key: Optional[str] = None
    supabase_jwt_secret: Optional[str] = None
    supabase_storage_bucket: str = "generated"

    # --- Dev auth fallback (used only when supabase_jwt_secret is unset) ---
    dev_user_id: str = "00000000-0000-0000-0000-000000000001"
    dev_user_email: str = "dev@local"

    # --- Facebook Login / Graph API (per-user Page connection) ---
    facebook_app_id: Optional[str] = None
    facebook_app_secret: Optional[str] = None
    facebook_graph_api_version: str = "v21.0"
    facebook_redirect_uri: Optional[str] = None  # https://<app>/connect/facebook/callback
    facebook_scopes: str = "pages_show_list,pages_read_engagement,pages_manage_posts"

    # --- Secrets ---
    fernet_key: Optional[str] = None  # Fernet.generate_key() — encrypts stored Page tokens
    internal_cron_secret: str = "change-me"
    approval_webhook_secret: str = "change-me"

    # --- App ---
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_base_url: str = "http://localhost:8000"
    data_dir: Path = BASE_DIR / "data"
    persona_template_file: Path = BASE_DIR / "target_persona.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()
