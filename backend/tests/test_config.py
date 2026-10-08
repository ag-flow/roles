"""Tests for the Settings module."""

from __future__ import annotations

import pytest


def test_settings_loads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings reads required values from environment variables."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setenv("MINIO_ENDPOINT", "http://minio:9000")
    monkeypatch.setenv("MINIO_ACCESS_KEY", "key")
    monkeypatch.setenv("MINIO_SECRET_KEY", "secret")

    from role_builder.config import Settings

    s = Settings()
    assert s.database_url == "postgresql://test:test@localhost/test"
    assert s.minio_endpoint == "http://minio:9000"
    assert s.minio_access_key == "key"
    assert s.minio_secret_key == "secret"
    assert s.log_level == "INFO"  # default
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
    # Sprint 6 — Scheduler
    assert s.disable_scheduler is False


def test_settings_sprint2_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sprint 2 env overrides flow into Settings (cookies, cap, image tag)."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setenv("MINIO_ENDPOINT", "http://minio:9000")
    monkeypatch.setenv("MINIO_ACCESS_KEY", "key")
    monkeypatch.setenv("MINIO_SECRET_KEY", "secret")
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


def _require_core(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pose les champs obligatoires, pour n'éprouver que le comportement testé."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setenv("MINIO_ENDPOINT", "http://minio:9000")
    monkeypatch.setenv("MINIO_ACCESS_KEY", "key")
    monkeypatch.setenv("MINIO_SECRET_KEY", "secret")


def test_settings_unknown_env_file_key_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Une clef inconnue du .env fait échouer le démarrage (fail closed).

    C'est la régression que extra="ignore" laissait passer : la clef était
    avalée et le défaut s'appliquait, loin de la cause.
    """
    from pydantic import ValidationError

    from role_builder.config import Settings

    _require_core(monkeypatch)
    env_file = tmp_path / ".env"
    # Faute de frappe volontaire sur LOG_LEVEL — valeur discriminante.
    env_file.write_text("LOG_LEVELL=DEBUG\n", encoding="utf-8")

    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=str(env_file))  # type: ignore[call-arg]
    assert any(e["type"] == "extra_forbidden" for e in exc.value.errors())


def test_settings_accepts_compose_only_keys(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Les clefs du .env qui appartiennent au compose ne bloquent pas le boot.

    Sans leur déclaration dans Settings, extra="forbid" refuserait le fichier
    entier — le .env de la cible est partagé entre compose et le backend.
    """
    from role_builder.config import Settings

    _require_core(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "POSTGRES_USER=rb_abcd1234\n"
        "POSTGRES_PASSWORD=s3cret-pg\n"
        "POSTGRES_DB=role_builder\n"
        "POSTGRES_PORT=5432\n"
        "MINIO_ROOT_USER=minioadmin_ab12\n"
        "MINIO_ROOT_PASSWORD=s3cret-minio\n"
        "MINIO_API_PORT=9000\n"
        "MINIO_CONSOLE_PORT=9001\n"
        "BACKEND_PORT=8000\n"
        "FRONTEND_PORT=3000\n"
        "IMAGE_TAG=latest\n"
        "HARPOCRATE_ALLOW_INSECURE=0\n"
        "KEYCLOAK_CLIENT_SECRET=s3cret-kc\n"
        "NEXTAUTH_SECRET=s3cret-na\n"
        "NEXTAUTH_URL=http://localhost:3000\n"
        "NEXT_PUBLIC_API_URL=http://localhost:8000\n",
        encoding="utf-8",
    )

    s = Settings(_env_file=str(env_file))  # type: ignore[call-arg]

    assert s.postgres_user == "rb_abcd1234"
    assert s.backend_port == 8000


def test_settings_compose_secrets_are_not_printable(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Un secret du compose ne doit pas apparaître dans la repr du modèle."""
    from role_builder.config import Settings

    _require_core(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text("POSTGRES_PASSWORD=discriminant-pg-value\n", encoding="utf-8")

    s = Settings(_env_file=str(env_file))  # type: ignore[call-arg]

    assert "discriminant-pg-value" not in repr(s)
    assert s.postgres_password.get_secret_value() == "discriminant-pg-value"
