"""Application configuration via environment variables."""
from __future__ import annotations

from uuid import UUID

from pydantic_settings import BaseSettings, SettingsConfigDict

# UUID stable du tenant unique en MVP mono-user. À retirer quand le multi-tenant
# sera réel (auth + extraction depuis le JWT).
TENANT_ID_DEFAULT = UUID("00000000-0000-0000-0000-000000000001")


class Settings(BaseSettings):
    """Settings loaded from environment variables / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    openbao_url: str
    openbao_token: str

    agflow_base_url: str = "https://docker-agflow.yoops.org"
    log_level: str = "INFO"

    # Sprint 2 — Scrapers
    youtube_cookies_b64: str = ""
    instagram_cookies_b64: str = ""
    tiktok_cookies_b64: str = ""
    max_concurrent_scrapers: int = 5
    scraper_image_tag: str = "latest"
    disable_orchestrator: bool = False
    disable_ws_relay: bool = False

    # Sprint 3 — Transcription (clés API SaaS, vides = fallback shared)
    openai_api_key: str = ""
    deepgram_api_key: str = ""
    assemblyai_api_key: str = ""
    speechmatics_api_key: str = ""
    # Workers user (provisioning + auto-stop loop interne backend)
    worker_auto_stop_threshold_s: int = 300
    worker_auto_stop_period_s: int = 60
    worker_image_tag: str = "latest"
    ghcr_owner: str = ""
    disable_worker_manager: bool = False

    # Phase A — Auth Keycloak
    keycloak_issuer_url: str = ""
    keycloak_client_id: str = ""
    keycloak_audience: str = ""
    disable_auth: bool = False

    # Sprint 4 — Mistral (LLM + embeddings) + chunking_worker
    mistral_api_key: str = ""
    mistral_base_url: str = "https://api.mistral.ai"
    mistral_embed_model: str = "mistral-embed"
    mistral_chat_model: str = "mistral-large-latest"
    disable_chunking_worker: bool = False


settings = Settings()  # type: ignore[call-arg]
