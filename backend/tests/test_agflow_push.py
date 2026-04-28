"""Tests TDD pour services/agflow/push.py."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest


def _make_project(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": uuid4(),
        "tenant_id": uuid4(),
        "display_name": "Agent Test",
        "description": "Un agent de test",
        "identity": "Je suis un agent spécialisé.",
        "language": "fr",
        "target_role_id": None,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Pool stub qui enregistre les `conn.execute(...)` (notamment pg_notify)
# ---------------------------------------------------------------------------


class _RecordingConn:
    def __init__(self, pool: _RecordingPool) -> None:
        self._pool = pool

    async def execute(self, query: str, *args: Any) -> str:
        self._pool.execute_calls.append((query, args))
        return "SELECT 1"


class _RecordingAcquire:
    def __init__(self, pool: _RecordingPool) -> None:
        self._pool = pool

    async def __aenter__(self) -> _RecordingConn:
        return _RecordingConn(self._pool)

    async def __aexit__(self, *_: Any) -> None:
        return None


class _RecordingPool:
    """Pool capable de `async with pool.acquire() as conn` qui enregistre les execute()."""

    def __init__(self) -> None:
        self.execute_calls: list[tuple[str, tuple[Any, ...]]] = []

    def acquire(self) -> _RecordingAcquire:
        return _RecordingAcquire(self)


def _extract_notify_payloads(
    pool: _RecordingPool,
) -> list[dict[str, Any]]:
    """Extrait les payloads JSON des pg_notify émis vers agflow_push_events."""
    payloads: list[dict[str, Any]] = []
    for query, args in pool.execute_calls:
        if "pg_notify" in query:
            assert args[0] == "agflow_push_events"
            payloads.append(json.loads(args[1]))
    return payloads


def _make_docs_by_section() -> dict[str, list[dict[str, Any]]]:
    return {
        "Role": [{"id": uuid4(), "section": "Role", "name": "doc_role", "content": "# Role"}],
        "Missions": [{"id": uuid4(), "section": "Missions", "name": "mission_1", "content": "# M"}],
        "Skills": [{"id": uuid4(), "section": "Skills", "name": "skill_1", "content": "# S"}],
    }


class _StubAdminClient:
    """Stub pour AgflowAdminClient."""

    def __init__(
        self,
        create_role_result: dict[str, Any] | None = None,
        import_result: dict[str, Any] | None = None,
    ) -> None:
        self.create_role_calls: list[dict[str, Any]] = []
        self.import_calls: list[tuple[str, bytes]] = []
        self.generate_calls: list[str] = []
        self._create_result = create_role_result or {"id": "new-agflow-role-id"}
        self._import_result = import_result or {"documents_count": 3}

    async def create_role(
        self, *, display_name: str, description: str | None = None
    ) -> dict[str, Any]:
        self.create_role_calls.append({"display_name": display_name, "description": description})
        return self._create_result

    async def import_role_zip(self, role_id: str, zip_bytes: bytes) -> dict[str, Any]:
        self.import_calls.append((role_id, zip_bytes))
        return self._import_result

    async def generate_prompts(self, role_id: str) -> dict[str, Any]:
        self.generate_calls.append(role_id)
        return {"status": "ok"}

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_push_creates_role_then_imports_zip(stubbed_env: None) -> None:
    """Happy path créer + push : project sans target_role_id → create_role + update_target_role_id + import_role_zip."""
    from role_builder.services.agflow import push as push_mod

    project = _make_project()
    docs = _make_docs_by_section()
    stub_client = _StubAdminClient()
    pool = MagicMock()

    with (
        patch.object(
            push_mod.role_projects, "get_by_id", new=AsyncMock(return_value=project)
        ),
        patch.object(
            push_mod.role_documents,
            "list_current_by_project_grouped",
            new=AsyncMock(return_value=docs),
        ),
        patch.object(
            push_mod.role_projects,
            "update_target_role_id",
            new=AsyncMock(),
        ) as mock_update,
    ):
        result = await push_mod.push_role_to_agflow(
            project["id"], pool=pool, client=stub_client
        )

    assert result["agflow_role_id"] == "new-agflow-role-id"
    assert "agflow_url" in result
    assert "new-agflow-role-id" in result["agflow_url"]
    assert result["prompt_generated"] is False
    # create_role appelé
    assert len(stub_client.create_role_calls) == 1
    assert stub_client.create_role_calls[0]["display_name"] == "Agent Test"
    # update_target_role_id appelé
    mock_update.assert_awaited_once()
    # import_role_zip appelé
    assert len(stub_client.import_calls) == 1
    assert stub_client.import_calls[0][0] == "new-agflow-role-id"
    # generate_prompts NON appelé
    assert len(stub_client.generate_calls) == 0


@pytest.mark.asyncio
async def test_push_republication_skips_create(stubbed_env: None) -> None:
    """Republication : project avec target_role_id existant → create_role PAS appelé."""
    from role_builder.services.agflow import push as push_mod

    project = _make_project(target_role_id="existing-agflow-role")
    docs = _make_docs_by_section()
    stub_client = _StubAdminClient()
    pool = MagicMock()

    with (
        patch.object(
            push_mod.role_projects, "get_by_id", new=AsyncMock(return_value=project)
        ),
        patch.object(
            push_mod.role_documents,
            "list_current_by_project_grouped",
            new=AsyncMock(return_value=docs),
        ),
        patch.object(
            push_mod.role_projects,
            "update_target_role_id",
            new=AsyncMock(),
        ) as mock_update,
    ):
        result = await push_mod.push_role_to_agflow(
            project["id"], pool=pool, client=stub_client
        )

    assert result["agflow_role_id"] == "existing-agflow-role"
    # create_role PAS appelé
    assert len(stub_client.create_role_calls) == 0
    # update_target_role_id PAS appelé non plus
    mock_update.assert_not_awaited()
    # import_role_zip appelé avec l'ID existant
    assert len(stub_client.import_calls) == 1
    assert stub_client.import_calls[0][0] == "existing-agflow-role"


@pytest.mark.asyncio
async def test_push_identity_missing_raises(stubbed_env: None) -> None:
    """Identity manquante → RuntimeError 'missing pieces'."""
    from role_builder.services.agflow import push as push_mod

    project = _make_project(identity=None)
    docs = _make_docs_by_section()
    stub_client = _StubAdminClient()
    pool = MagicMock()

    with (
        patch.object(
            push_mod.role_projects, "get_by_id", new=AsyncMock(return_value=project)
        ),
        patch.object(
            push_mod.role_documents,
            "list_current_by_project_grouped",
            new=AsyncMock(return_value=docs),
        ),
    ):
        with pytest.raises(RuntimeError, match="missing pieces"):
            await push_mod.push_role_to_agflow(
                project["id"], pool=pool, client=stub_client
            )


@pytest.mark.asyncio
async def test_push_skills_section_empty_raises(stubbed_env: None) -> None:
    """Section Skills sans docs → RuntimeError 'missing pieces'."""
    from role_builder.services.agflow import push as push_mod

    project = _make_project()
    # Skills absent
    docs: dict[str, list[dict[str, Any]]] = {
        "Role": [{"id": uuid4(), "section": "Role", "name": "doc_role", "content": "# Role"}],
        "Missions": [{"id": uuid4(), "section": "Missions", "name": "m1", "content": "# M"}],
    }
    stub_client = _StubAdminClient()
    pool = MagicMock()

    with (
        patch.object(
            push_mod.role_projects, "get_by_id", new=AsyncMock(return_value=project)
        ),
        patch.object(
            push_mod.role_documents,
            "list_current_by_project_grouped",
            new=AsyncMock(return_value=docs),
        ),
    ):
        with pytest.raises(RuntimeError, match="missing pieces"):
            await push_mod.push_role_to_agflow(
                project["id"], pool=pool, client=stub_client
            )


@pytest.mark.asyncio
async def test_push_project_not_found_raises(stubbed_env: None) -> None:
    """Project introuvable → RuntimeError 'not found'."""
    from role_builder.services.agflow import push as push_mod

    project_id = uuid4()
    stub_client = _StubAdminClient()
    pool = MagicMock()

    with patch.object(
        push_mod.role_projects, "get_by_id", new=AsyncMock(return_value=None)
    ):
        with pytest.raises(RuntimeError, match="not found"):
            await push_mod.push_role_to_agflow(project_id, pool=pool, client=stub_client)


@pytest.mark.asyncio
async def test_push_with_generate_prompts_flag(stubbed_env: None) -> None:
    """generate_prompts=True → generate_prompts appelé, prompt_generated=True."""
    from role_builder.services.agflow import push as push_mod

    project = _make_project()
    docs = _make_docs_by_section()
    stub_client = _StubAdminClient()
    pool = MagicMock()

    with (
        patch.object(
            push_mod.role_projects, "get_by_id", new=AsyncMock(return_value=project)
        ),
        patch.object(
            push_mod.role_documents,
            "list_current_by_project_grouped",
            new=AsyncMock(return_value=docs),
        ),
        patch.object(
            push_mod.role_projects,
            "update_target_role_id",
            new=AsyncMock(),
        ),
    ):
        result = await push_mod.push_role_to_agflow(
            project["id"], generate_prompts=True, pool=pool, client=stub_client
        )

    assert result["prompt_generated"] is True
    assert len(stub_client.generate_calls) == 1
    assert stub_client.generate_calls[0] == "new-agflow-role-id"


@pytest.mark.asyncio
async def test_push_generate_prompts_false_not_called(stubbed_env: None) -> None:
    """generate_prompts=False (défaut) → generate_prompts NON appelé, prompt_generated=False."""
    from role_builder.services.agflow import push as push_mod

    project = _make_project()
    docs = _make_docs_by_section()
    stub_client = _StubAdminClient()
    pool = MagicMock()

    with (
        patch.object(
            push_mod.role_projects, "get_by_id", new=AsyncMock(return_value=project)
        ),
        patch.object(
            push_mod.role_documents,
            "list_current_by_project_grouped",
            new=AsyncMock(return_value=docs),
        ),
        patch.object(
            push_mod.role_projects,
            "update_target_role_id",
            new=AsyncMock(),
        ),
    ):
        result = await push_mod.push_role_to_agflow(
            project["id"], generate_prompts=False, pool=pool, client=stub_client
        )

    assert result["prompt_generated"] is False
    assert len(stub_client.generate_calls) == 0


def test_check_missing_pieces_all_ok() -> None:
    """check_missing_pieces → liste vide si tout est OK."""
    from role_builder.services.agflow.push import check_missing_pieces

    project = _make_project()
    docs = _make_docs_by_section()

    missing = check_missing_pieces(project, docs)

    assert missing == []


def test_check_missing_pieces_identity_null() -> None:
    """check_missing_pieces → contient 'Identity not generated' si identity null."""
    from role_builder.services.agflow.push import check_missing_pieces

    project = _make_project(identity=None)
    docs = _make_docs_by_section()

    missing = check_missing_pieces(project, docs)

    assert any("Identity" in m for m in missing)


def test_check_missing_pieces_role_section_empty() -> None:
    """check_missing_pieces → contient 'Section Role has no current documents'."""
    from role_builder.services.agflow.push import check_missing_pieces

    project = _make_project()
    docs: dict[str, list[dict[str, Any]]] = {
        "Missions": [{"name": "m1"}],
        "Skills": [{"name": "s1"}],
    }

    missing = check_missing_pieces(project, docs)

    assert any("Role" in m for m in missing)
    assert not any("Missions" in m for m in missing)
    assert not any("Skills" in m for m in missing)


def test_check_missing_pieces_skills_empty() -> None:
    """check_missing_pieces → contient 'Section Skills has no current documents'."""
    from role_builder.services.agflow.push import check_missing_pieces

    project = _make_project()
    docs: dict[str, list[dict[str, Any]]] = {
        "Role": [{"name": "r1"}],
        "Missions": [{"name": "m1"}],
    }

    missing = check_missing_pieces(project, docs)

    assert any("Skills" in m for m in missing)
    assert not any("Role" in m for m in missing)
    assert not any("Missions" in m for m in missing)


# ---------------------------------------------------------------------------
# D0.2.2 — Émission pg_notify(agflow_push_events) à chaque étape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_push_emits_notify_steps_in_order_with_generate_prompts(
    stubbed_env: None,
) -> None:
    """Happy path avec generate_prompts=True émet zip_built → role_ready
    → zip_uploaded → prompts_generated → done dans cet ordre."""
    from role_builder.services.agflow import push as push_mod

    project = _make_project()
    docs = _make_docs_by_section()
    stub_client = _StubAdminClient()
    pool = _RecordingPool()

    with (
        patch.object(
            push_mod.role_projects, "get_by_id", new=AsyncMock(return_value=project)
        ),
        patch.object(
            push_mod.role_documents,
            "list_current_by_project_grouped",
            new=AsyncMock(return_value=docs),
        ),
        patch.object(
            push_mod.role_projects,
            "update_target_role_id",
            new=AsyncMock(),
        ),
    ):
        await push_mod.push_role_to_agflow(
            project["id"], generate_prompts=True, pool=pool, client=stub_client
        )

    payloads = _extract_notify_payloads(pool)
    steps = [p["step"] for p in payloads]
    assert steps == [
        "zip_built",
        "role_ready",
        "zip_uploaded",
        "prompts_generated",
        "done",
    ]
    # Tous les payloads portent le bon tenant_id et project_id
    assert all(p["tenant_id"] == str(project["tenant_id"]) for p in payloads)
    assert all(p["project_id"] == str(project["id"]) for p in payloads)
    # Statuts : in_progress sauf le dernier (done)
    assert payloads[-1]["status"] == "done"
    assert all(p["status"] == "in_progress" for p in payloads[:-1])


@pytest.mark.asyncio
async def test_push_emits_steps_without_prompts_generated_when_flag_false(
    stubbed_env: None,
) -> None:
    """generate_prompts=False : pas d'événement prompts_generated."""
    from role_builder.services.agflow import push as push_mod

    project = _make_project()
    docs = _make_docs_by_section()
    stub_client = _StubAdminClient()
    pool = _RecordingPool()

    with (
        patch.object(
            push_mod.role_projects, "get_by_id", new=AsyncMock(return_value=project)
        ),
        patch.object(
            push_mod.role_documents,
            "list_current_by_project_grouped",
            new=AsyncMock(return_value=docs),
        ),
        patch.object(
            push_mod.role_projects,
            "update_target_role_id",
            new=AsyncMock(),
        ),
    ):
        await push_mod.push_role_to_agflow(
            project["id"], generate_prompts=False, pool=pool, client=stub_client
        )

    steps = [p["step"] for p in _extract_notify_payloads(pool)]
    assert steps == ["zip_built", "role_ready", "zip_uploaded", "done"]
    assert "prompts_generated" not in steps


class _FailingOnImportClient(_StubAdminClient):
    """Client stub qui lève httpx.ConnectError sur import_role_zip."""

    async def import_role_zip(self, role_id: str, zip_bytes: bytes) -> dict[str, Any]:
        raise httpx.ConnectError("simulated network error")


@pytest.mark.asyncio
async def test_push_emits_failed_event_when_import_raises(stubbed_env: None) -> None:
    """Si import_role_zip échoue, le push émet zip_built, role_ready puis failed
    avec status=failed et detail.error."""
    from role_builder.services.agflow import push as push_mod

    project = _make_project()
    docs = _make_docs_by_section()
    stub_client = _FailingOnImportClient()
    pool = _RecordingPool()

    with (
        patch.object(
            push_mod.role_projects, "get_by_id", new=AsyncMock(return_value=project)
        ),
        patch.object(
            push_mod.role_documents,
            "list_current_by_project_grouped",
            new=AsyncMock(return_value=docs),
        ),
        patch.object(
            push_mod.role_projects,
            "update_target_role_id",
            new=AsyncMock(),
        ),
    ):
        with pytest.raises(httpx.HTTPError):
            await push_mod.push_role_to_agflow(
                project["id"], generate_prompts=False, pool=pool, client=stub_client
            )

    payloads = _extract_notify_payloads(pool)
    steps = [p["step"] for p in payloads]
    statuses = [p["status"] for p in payloads]
    # Au moins un zip_built et un failed avant que ça crashe
    assert "zip_built" in steps
    assert "role_ready" in steps
    assert steps[-1] == "failed"
    assert statuses[-1] == "failed"
    # Le payload failed contient l'erreur
    assert "error" in payloads[-1].get("detail", {})


@pytest.mark.asyncio
async def test_push_notify_failure_does_not_break_push(stubbed_env: None) -> None:
    """Si _emit lève (ex: pool indisponible), le push ne casse pas
    (best-effort logging only)."""
    from role_builder.services.agflow import push as push_mod

    project = _make_project()
    docs = _make_docs_by_section()
    stub_client = _StubAdminClient()
    pool = MagicMock()  # pool qui ne supporte PAS `async with` → _emit échoue silencieusement

    with (
        patch.object(
            push_mod.role_projects, "get_by_id", new=AsyncMock(return_value=project)
        ),
        patch.object(
            push_mod.role_documents,
            "list_current_by_project_grouped",
            new=AsyncMock(return_value=docs),
        ),
        patch.object(
            push_mod.role_projects,
            "update_target_role_id",
            new=AsyncMock(),
        ),
    ):
        result = await push_mod.push_role_to_agflow(
            project["id"], pool=pool, client=stub_client
        )

    # Le push réussit malgré les notify qui ont échoué
    assert result["agflow_role_id"] == "new-agflow-role-id"
