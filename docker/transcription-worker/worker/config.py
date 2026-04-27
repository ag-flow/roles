"""Worker config via Pydantic Settings."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration du worker, alimentée par env vars passées au container."""

    model_config = SettingsConfigDict(extra="ignore")

    # Identifiant logique du pool ('shared_default' ou 'user_<uuid>')
    worker_pool_id: str
    # Identifiant unique du worker (container_name typiquement)
    worker_id: str
    # Provider à instancier
    transcription_provider: str  # 'faster-whisper' | 'openai-whisper' | ...

    # Connexion DB partagée avec le backend
    database_url: str

    # MinIO
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str

    # Cadence du polling (s)
    poll_interval_s: float = 2.0

    # Provider-spécifique
    openai_api_key: str = ""
    deepgram_api_key: str = ""
    assemblyai_api_key: str = ""
    speechmatics_api_key: str = ""

    # faster-whisper
    faster_whisper_model: str = "large-v3"
    faster_whisper_device: str = "auto"  # auto|cpu|cuda
    faster_whisper_compute_type: str = "float16"  # float16 sur GPU, int8 sur CPU


settings = Settings()  # type: ignore[call-arg]
