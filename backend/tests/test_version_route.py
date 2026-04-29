"""Tests pour la route /api/version."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_version_returns_current_version_and_name(client: TestClient) -> None:
    """GET /api/version retourne {version, name} et fait remonter __version__."""
    from role_builder import __version__

    resp = client.get("/api/version")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["version"] == __version__
    assert body["name"] == "Role Builder"


def test_version_does_not_require_auth(client: TestClient) -> None:
    """L'endpoint /version est public (pas de Depends(get_current_user))."""
    # La fixture client a disable_auth=True ; la requête sans header doit passer.
    # On vérifie aussi qu'aucune validation Bearer n'est tentée (pas de WWW-Authenticate).
    resp = client.get("/api/version")
    assert resp.status_code == 200
    assert "WWW-Authenticate" not in resp.headers
