"""Tests TDD pour routes/apps.py — menu hamburger d'apps."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient


def _write_apps(path: Path, payload: Any) -> None:
    import json
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_get_apps_returns_entries_when_file_valid(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from role_builder.config import settings as _settings

    apps_file = tmp_path / "apps.json"
    _write_apps(apps_file, {
        "urls": [
            {
                "key": "docker", "label": "Docker",
                "icon": "https://docker-agflow.yoops.org/favicon.ico",
                "url": "https://docker-agflow.yoops.org/",
            },
            {
                "key": "security", "label": "Security",
                "icon": "https://security.yoops.org/favicon.ico",
                "url": "https://security.yoops.org/",
            },
        ],
    })
    monkeypatch.setattr(_settings, "apps_file", str(apps_file), raising=False)

    resp = client.get("/api/admin/apps")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["urls"]) == 2
    assert body["urls"][0]["key"] == "docker"
    assert body["urls"][1]["label"] == "Security"


def test_get_apps_returns_empty_when_file_missing(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from role_builder.config import settings as _settings

    monkeypatch.setattr(
        _settings, "apps_file", str(tmp_path / "absent.json"), raising=False,
    )
    resp = client.get("/api/admin/apps")
    assert resp.status_code == 200
    assert resp.json() == {"urls": []}


def test_get_apps_returns_empty_when_json_invalid(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from role_builder.config import settings as _settings

    apps_file = tmp_path / "apps.json"
    apps_file.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(_settings, "apps_file", str(apps_file), raising=False)

    resp = client.get("/api/admin/apps")
    assert resp.status_code == 200
    assert resp.json() == {"urls": []}


def test_get_apps_skips_invalid_entries_keeps_valid(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Une entrée mal formée (URL invalide, champ manquant) est skip,
    les autres restent."""
    from role_builder.config import settings as _settings

    apps_file = tmp_path / "apps.json"
    _write_apps(apps_file, {
        "urls": [
            {
                "key": "ok", "label": "OK",
                "icon": "https://x.example/favicon.ico",
                "url": "https://x.example/",
            },
            {"key": "broken", "label": "Broken"},  # icon + url manquants
            {
                "key": "ok2", "label": "OK2",
                "icon": "https://y.example/favicon.ico",
                "url": "https://y.example/",
            },
        ],
    })
    monkeypatch.setattr(_settings, "apps_file", str(apps_file), raising=False)

    resp = client.get("/api/admin/apps")
    body = resp.json()
    assert len(body["urls"]) == 2
    keys = {u["key"] for u in body["urls"]}
    assert keys == {"ok", "ok2"}


def test_get_apps_returns_empty_when_urls_not_list(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from role_builder.config import settings as _settings

    apps_file = tmp_path / "apps.json"
    _write_apps(apps_file, {"urls": "not-a-list"})
    monkeypatch.setattr(_settings, "apps_file", str(apps_file), raising=False)

    resp = client.get("/api/admin/apps")
    assert resp.status_code == 200
    assert resp.json() == {"urls": []}
