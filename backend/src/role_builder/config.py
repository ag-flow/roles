"""Application configuration via environment variables."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


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


settings = Settings()  # type: ignore[call-arg]
