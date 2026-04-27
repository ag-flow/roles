"""MinIO upload helper for the YouTube scraper container (stub, see Task A6)."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def upload_audio(local_path: Path, cfg: dict[str, Any], item_id: str) -> str:
    """Placeholder for the upload helper. Real implementation in Task A6.

    This stub exists so that ``download.py`` can import the module (and tests can
    monkeypatch the symbol) before A6 ships the actual MinIO logic.
    """
    raise NotImplementedError("upload_audio: see Task A6")
