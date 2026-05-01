"""Tests pour routes.prompts — GET list, GET versions, POST version, PUT system-default."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient


def _make_prompt_row(name: str = "extractor") -> dict[str, Any]:
    return {
        "id": uuid4(),
        "name": name,
        "type": name,
        "target_section": None,
        "description": f"Description de {name}",
    }


def _make_version_row(prompt_id: UUID, version_number: int = 1) -> dict[str, Any]:
    return {
        "id": uuid4(),
        "prompt_id": prompt_id,
        "version_number": version_number,
        "template": "Template text...",
        "is_system_default": True,
        "created_at": datetime.now(tz=UTC),
    }


def test_get_prompts_returns_list(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /api/prompts retourne la liste des prompts."""
    from role_builder.routes import prompts as prompts_route

    rows = [_make_prompt_row("extractor"), _make_prompt_row("clusterer")]

    async def fake_list_prompts(*, pool: Any) -> list[dict[str, Any]]:
        return rows

    monkeypatch.setattr(prompts_route.prompts_helper, "list_prompts", fake_list_prompts)

    resp = client.get("/api/prompts")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 2
    assert body[0]["name"] == "extractor"
    assert body[1]["name"] == "clusterer"


def test_get_prompt_versions_returns_list(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GET /api/prompts/{prompt_id}/versions retourne la liste des versions."""
    from role_builder.routes import prompts as prompts_route

    prompt_id = uuid4()
    rows = [_make_version_row(prompt_id, 2), _make_version_row(prompt_id, 1)]

    async def fake_list_versions(pid: UUID, *, pool: Any) -> list[dict[str, Any]]:
        assert pid == prompt_id
        return rows

    monkeypatch.setattr(prompts_route.prompts_helper, "list_versions", fake_list_versions)

    resp = client.get(f"/api/prompts/{prompt_id}/versions")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 2
    assert body[0]["version_number"] == 2
    assert body[1]["version_number"] == 1


def test_post_version_creates_new_version(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /api/prompts/{prompt_id}/versions crée une nouvelle version user."""
    from role_builder.routes import prompts as prompts_route

    prompt_id = uuid4()
    new_version_id = uuid4()

    existing_versions = [_make_version_row(prompt_id, 1)]
    created_version = _make_version_row(prompt_id, 2)
    created_version["id"] = new_version_id
    created_version["is_system_default"] = False

    async def fake_list_versions(pid: UUID, *, pool: Any) -> list[dict[str, Any]]:
        return existing_versions

    async def fake_insert_prompt_version(**kwargs: Any) -> UUID:
        assert kwargs["version_number"] == 2
        assert kwargs["is_system_default"] is False
        assert kwargs["template"] == "Nouveau template"
        return new_version_id

    async def fake_get_version_by_id(vid: UUID, *, pool: Any) -> dict[str, Any]:
        assert vid == new_version_id
        return created_version

    monkeypatch.setattr(prompts_route.prompts_helper, "list_versions", fake_list_versions)
    monkeypatch.setattr(
        prompts_route.prompts_helper, "insert_prompt_version", fake_insert_prompt_version
    )
    monkeypatch.setattr(prompts_route.prompts_helper, "get_version_by_id", fake_get_version_by_id)

    resp = client.post(
        f"/api/prompts/{prompt_id}/versions",
        json={"template": "Nouveau template"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["id"] == str(new_version_id)
    assert body["version_number"] == 2
    assert body["is_system_default"] is False


def test_put_system_default_returns_204(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PUT /api/prompts/{prompt_id}/system-default/{version_id} retourne 204."""
    from role_builder.routes import prompts as prompts_route

    prompt_id = uuid4()
    version_id = uuid4()

    called: dict[str, Any] = {}

    async def fake_set_system_default(pid: UUID, vid: UUID, *, pool: Any) -> None:
        called["prompt_id"] = pid
        called["version_id"] = vid

    async def fake_mark_obsolete(
        pid: UUID, *, except_version_id: UUID, pool: Any,
    ) -> int:
        called["mark_obsolete_prompt_id"] = pid
        called["mark_obsolete_except"] = except_version_id
        return 0

    monkeypatch.setattr(prompts_route.prompts_helper, "set_system_default", fake_set_system_default)
    monkeypatch.setattr(prompts_route.runs_helper, "mark_obsolete_for_prompt", fake_mark_obsolete)

    resp = client.put(f"/api/prompts/{prompt_id}/system-default/{version_id}")
    assert resp.status_code == 204, resp.text
    assert called["prompt_id"] == prompt_id
    assert called["version_id"] == version_id


def test_put_system_default_marks_old_runs_obsolete(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Phase 2 sous-projet C : PUT system-default propage l'obsolescence
    aux runs ayant utilisé une autre version de ce prompt."""
    from role_builder.routes import prompts as prompts_route

    prompt_id = uuid4()
    version_id = uuid4()
    obsolete_calls: list[tuple[UUID, UUID]] = []

    async def fake_set(pid: UUID, vid: UUID, *, pool: Any) -> None:
        return None

    async def fake_mark_obsolete(
        pid: UUID, *, except_version_id: UUID, pool: Any,
    ) -> int:
        obsolete_calls.append((pid, except_version_id))
        return 4

    monkeypatch.setattr(prompts_route.prompts_helper, "set_system_default", fake_set)
    monkeypatch.setattr(prompts_route.runs_helper, "mark_obsolete_for_prompt", fake_mark_obsolete)

    resp = client.put(f"/api/prompts/{prompt_id}/system-default/{version_id}")
    assert resp.status_code == 204
    assert obsolete_calls == [(prompt_id, version_id)]


def test_put_system_default_returns_404_when_version_not_in_prompt(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PUT system-default retourne 404 si version_id n'appartient pas au prompt."""
    from role_builder.routes import prompts as prompts_route

    prompt_id = uuid4()
    wrong_version_id = uuid4()

    async def fake_set_system_default_raises(pid: UUID, vid: UUID, *, pool: Any) -> None:
        raise ValueError("version_id does not belong to prompt_id")

    monkeypatch.setattr(
        prompts_route.prompts_helper, "set_system_default", fake_set_system_default_raises
    )

    resp = client.put(f"/api/prompts/{prompt_id}/system-default/{wrong_version_id}")
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "version not found for this prompt"
