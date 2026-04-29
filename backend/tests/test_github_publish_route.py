"""Tests routes Sprint 8 — GitHub publish (repos + config + publish + history)."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# GET /api/github/repos
# ---------------------------------------------------------------------------


def test_list_repos_400_when_not_connected(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import github_publish as route

    async def fake_get(user_id: UUID, *, pool: Any) -> Any:
        return None

    monkeypatch.setattr(route.github_integrations, "get_by_user_id", fake_get)

    resp = client.get("/api/github/repos")
    assert resp.status_code == 400


def test_list_repos_returns_subset_of_fields(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import github_publish as route
    from role_builder.services.openbao_client import OpenBaoClient

    async def fake_get(user_id: UUID, *, pool: Any) -> Any:
        return {"openbao_path": "github-tokens/t/u"}

    async def fake_token(self: Any, path: str) -> Any:
        return {"access_token": "ghp_x"}

    async def fake_aclose(self: Any) -> None:
        return None

    monkeypatch.setattr(route.github_integrations, "get_by_user_id", fake_get)
    monkeypatch.setattr(OpenBaoClient, "get", fake_token)
    monkeypatch.setattr(OpenBaoClient, "aclose", fake_aclose)

    repos_full = [
        {
            "full_name": "alice/role-pack",
            "private": False,
            "default_branch": "main",
            "html_url": "https://github.com/alice/role-pack",
            "stargazers_count": 5,
            "ignored_field": "value",
        }
    ]

    class _StubApiClient:
        def __init__(self, *, access_token: str) -> None:
            assert access_token == "ghp_x"

        async def list_repos(self) -> list[dict[str, Any]]:
            return repos_full

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(route, "GitHubApiClient", _StubApiClient)

    resp = client.get("/api/github/repos")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    # Seuls les champs pertinents sont exposés
    assert set(body[0].keys()) == {
        "full_name",
        "private",
        "default_branch",
        "html_url",
    }
    assert body[0]["full_name"] == "alice/role-pack"


# ---------------------------------------------------------------------------
# GET / PUT publication-config
# ---------------------------------------------------------------------------


def test_get_publication_config_returns_404_when_unconfigured(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import github_publish as route

    async def fake_get(project_id: UUID, *, pool: Any) -> Any:
        return None

    monkeypatch.setattr(route.role_publication_config, "get_by_project_id", fake_get)

    resp = client.get(f"/api/role-projects/{uuid4()}/publication-config")
    assert resp.status_code == 404


def test_get_publication_config_returns_config_when_present(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import github_publish as route

    project_id = uuid4()

    async def fake_get(pid: UUID, *, pool: Any) -> Any:
        return {
            "role_project_id": project_id,
            "repo_full_name": "alice/roles",
            "target_subdirectory": "ux-clea",
            "branch": "main",
            "commit_message_template": "Update {role_name}",
            "license_choice": "cc-by-nc-sa-4.0",
        }

    monkeypatch.setattr(route.role_publication_config, "get_by_project_id", fake_get)

    resp = client.get(f"/api/role-projects/{project_id}/publication-config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["repo_full_name"] == "alice/roles"
    assert body["license_choice"] == "cc-by-nc-sa-4.0"


def test_put_publication_config_upserts_with_license_choice(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import github_publish as route

    project_id = uuid4()
    upsert_calls: list[dict[str, Any]] = []

    async def fake_upsert(**kwargs: Any) -> None:
        upsert_calls.append(kwargs)

    monkeypatch.setattr(route.role_publication_config, "upsert", fake_upsert)

    resp = client.put(
        f"/api/role-projects/{project_id}/publication-config",
        json={
            "repo_full_name": "alice/roles",
            "target_subdirectory": "ux-clea",
            "branch": "main",
            "commit_message_template": "Update {role_name}",
            "license_choice": "cc-by-nc-sa-4.0",
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"status": "saved"}
    assert len(upsert_calls) == 1
    assert upsert_calls[0]["license_choice"] == "cc-by-nc-sa-4.0"
    assert str(upsert_calls[0]["role_project_id"]) == str(project_id)


def test_put_publication_config_rejects_invalid_license(client: TestClient) -> None:
    """license_choice doit être dans le Literal, sinon 422."""
    resp = client.put(
        f"/api/role-projects/{uuid4()}/publication-config",
        json={
            "repo_full_name": "alice/roles",
            "target_subdirectory": "x",
            "license_choice": "GPL-3.0",
        },
    )
    assert resp.status_code == 422


def test_put_publication_config_with_minimal_body_uses_defaults(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sans branch/commit_message_template/license_choice, les defaults Pydantic s'appliquent."""
    from role_builder.routes import github_publish as route

    upsert_calls: list[dict[str, Any]] = []

    async def fake_upsert(**kwargs: Any) -> None:
        upsert_calls.append(kwargs)

    monkeypatch.setattr(route.role_publication_config, "upsert", fake_upsert)

    resp = client.put(
        f"/api/role-projects/{uuid4()}/publication-config",
        json={
            "repo_full_name": "alice/roles",
            "target_subdirectory": "x",
        },
    )
    assert resp.status_code == 200
    assert upsert_calls[0]["branch"] == "main"
    assert upsert_calls[0]["license_choice"] == "none"
