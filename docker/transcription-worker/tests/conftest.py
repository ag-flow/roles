"""Conftest commun aux tests worker — fournit les env vars minimales pour Settings().

worker/config.py instancie `Settings()` à l'import, ce qui exige toutes les
variables required (worker_pool_id, worker_id, transcription_provider,
database_url, minio_*). On les pose ici avant que tout module worker.* ne soit
importé par les tests.
"""
from __future__ import annotations

import os

_DEFAULTS = {
    "WORKER_POOL_ID": "shared_default",
    "WORKER_ID": "rb-worker-test-1",
    "TRANSCRIPTION_PROVIDER": "openai-whisper",
    "DATABASE_URL": "postgresql://test:test@localhost/test",
    "MINIO_ENDPOINT": "http://localhost:9000",
    "MINIO_ACCESS_KEY": "test",
    "MINIO_SECRET_KEY": "test",
    "OPENAI_API_KEY": "sk-test",
}

for _k, _v in _DEFAULTS.items():
    os.environ.setdefault(_k, _v)
