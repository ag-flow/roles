"""Tests TDD pour services/agflow/push.py."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


def _make_project(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": uuid4(),
        "display_name": "Agent Test",
        "description": "Un agent de test",
        "identity": "Je suis un agent spécialisé.",
        "language": "fr",
        "target_role_id": None,
    }
    base.update(overrides)
    return base


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
