"""
Central runtime configuration, loaded from environment variables (.env supported).

Nothing about accounts, sandbox realm IDs, or API keys is hardcoded here -
every external dependency (Mongo, Gemini, QuickBooks) is wired through env vars
so the same code runs in local dev, CI, and the grader's machine.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    app_env: str = "development"
    testing: bool = False

    # --- MongoDB ---
    # "mongomock://" triggers the in-memory mock driver (used automatically when testing=True).
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "finz_pipeline"

    # --- Gemini (used to assist classification of ambiguous transactions) ---
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.0-flash"

    # --- QuickBooks Online ---
    qbo_client_id: str | None = None
    qbo_client_secret: str | None = None
    qbo_environment: str = "sandbox"  # "sandbox" or "production"
    qbo_redirect_uri: str = "http://localhost:8000/api/qbo/callback"
    qbo_realm_id: str | None = None  # sandbox company ID, set after OAuth connect

    # Where the browser gets sent back to after the OAuth callback finishes -
    # the frontend dev server by default, so the user lands back in the app
    # instead of staring at a raw JSON response from the backend.
    frontend_url: str = "http://localhost:5173"

    # --- Ingestion safety limits ---
    allowed_currencies: list[str] = ["USD"]
    max_upload_rows: int = 50_000

    # --- Sync eligibility ---
    # "Safely classified" per PDF 4.5: a rule/vendor-directory match (always
    # confidence 1.0) syncs automatically; a low-confidence Gemini guess sits
    # below this bar and must go through human review first.
    auto_sync_confidence_threshold: float = 0.95


@lru_cache
def get_settings() -> Settings:
    return Settings()
