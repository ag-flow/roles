"""Tests for the Settings module."""

from __future__ import annotations

import pytest


def test_settings_loads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings reads required values from environment variables."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setenv("MINIO_ENDPOINT", "http://minio:9000")
    monkeypatch.setenv("MINIO_ACCESS_KEY", "key")
    monkeypatch.setenv("MINIO_SECRET_KEY", "secret")
    monkeypatch.setenv("OPENBAO_URL", "http://bao:8200")
    monkeypatch.setenv("OPENBAO_TOKEN", "token")

    from role_builder.config import Settings

    s = Settings()
    assert s.database_url == "postgresql://test:test@localhost/test"
    assert s.minio_endpoint == "http://minio:9000"
    assert s.minio_access_key == "key"
    assert s.minio_secret_key == "secret"
    assert s.openbao_url == "http://bao:8200"
    assert s.openbao_token == "token"
    assert s.log_level == "INFO"  # default
    assert s.agflow_base_url == "https://docker-agflow.yoops.org"  # default
    # Sprint 2 Phase C defaults
    assert s.youtube_cookies_b64 == ""
    assert s.instagram_cookies_b64 == ""
    assert s.tiktok_cookies_b64 == ""
    assert s.max_concurrent_scrapers == 5
    assert s.scraper_image_tag == "latest"
    # Sprint 3 Phase G4 defaults — transcription
    assert s.openai_api_key == ""
    assert s.deepgram_api_key == ""
    assert s.assemblyai_api_key == ""
    assert s.speechmatics_api_key == ""
    assert s.worker_auto_stop_threshold_s == 300
    assert s.worker_auto_stop_period_s == 60
    assert s.worker_image_tag == "latest"
    assert s.ghcr_owner == ""
    assert s.disable_worker_manager is False
    # Auth Keycloak — Phase A
    assert s.keycloak_issuer_url == ""
    assert s.keycloak_client_id == ""
    assert s.keycloak_audience == ""
    assert s.disable_auth is False
    # Sprint 4 — Mistral defaults + chunking_worker
    assert s.mistral_api_key == ""
    assert s.mistral_base_url == "https://api.mistral.ai"
    assert s.mistral_embed_model == "mistral-embed"
    assert s.mistral_chat_model == "mistral-large-latest"
    assert s.disable_chunking_worker is False
    # Sprint 5 — Cost tracking Mistral
    assert s.mistral_input_token_rate_usd == 0.000002
    assert s.mistral_output_token_rate_usd == 0.000006


def test_settings_sprint2_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sprint 2 env overrides flow into Settings (cookies, cap, image tag)."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setenv("MINIO_ENDPOINT", "http://minio:9000")
    monkeypatch.setenv("MINIO_ACCESS_KEY", "key")
    monkeypatch.setenv("MINIO_SECRET_KEY", "secret")
    monkeypatch.setenv("OPENBAO_URL", "http://bao:8200")
    monkeypatch.setenv("OPENBAO_TOKEN", "token")
    monkeypatch.setenv("YOUTUBE_COOKIES_B64", "yt-cookies")
    monkeypatch.setenv("INSTAGRAM_COOKIES_B64", "ig-cookies")
    monkeypatch.setenv("TIKTOK_COOKIES_B64", "tt-cookies")
    monkeypatch.setenv("MAX_CONCURRENT_SCRAPERS", "12")
    monkeypatch.setenv("SCRAPER_IMAGE_TAG", "sha-deadbeef")

    from role_builder.config import Settings

    s = Settings()
    assert s.youtube_cookies_b64 == "yt-cookies"
    assert s.instagram_cookies_b64 == "ig-cookies"
    assert s.tiktok_cookies_b64 == "tt-cookies"
    assert s.max_concurrent_scrapers == 12
    assert s.scraper_image_tag == "sha-deadbeef"
