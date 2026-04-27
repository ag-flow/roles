"""Tests TDD pour synthesis/decomposer.py — run_decomposition pipeline."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

import pytest

from role_builder.services.agflow_client import ChatResult

# ---------------------------------------------------------------------------
# Stubs asyncpg pool
# ---------------------------------------------------------------------------


class _StubConn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, tuple[Any, ...]]] = []
        self.fetchval_return: Any = None
        self.fetchrow_return: Any = None
        self.fetch_return: list[Any] = []
        self.execute_return: str = "DELETE 0"

    async def fetchval(self, query: str, *args: Any) -> Any:
        self.calls.append(("fetchval", query, args))
        return self.fetchval_return

    async def fetchrow(self, query: str, *args: Any) -> Any:
        self.calls.append(("fetchrow", query, args))
        return self.fetchrow_return

    async def fetch(self, query: str, *args: Any) -> list[Any]:
        self.calls.append(("fetch", query, args))
        return self.fetch_return

    async def execute(self, query: str, *args: Any) -> str:
        self.calls.append(("execute", query, args))
        return self.execute_return


class _StubAcquireCtx:
    def __init__(self, conn: _StubConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _StubConn:
        return self._conn

    async def __aexit__(self, *_: Any) -> None:
        return None


class _StubPool:
    def __init__(self, conn: _StubConn) -> None:
        self._conn = conn

    def acquire(self) -> _StubAcquireCtx:
        return _StubAcquireCtx(self._conn)


# ---------------------------------------------------------------------------
# Stub agflow_client
# ---------------------------------------------------------------------------


class _StubClient:
    """Stub AgflowClient avec réponse pré-réglée et capture des appels."""

    def __init__(self, content: str, model: str = "mistral-test") -> None:
        self._content = content
        self._model = model
        self.calls: list[tuple[list[dict], dict | None]] = []

    async def invoke_chat(
        self, messages: list[dict], *, response_format: dict | None = None
    ) -> ChatResult:
        self.calls.append((messages, response_format))
        return ChatResult(
            content=self._content,
            tokens_input=10,
            tokens_output=20,
            cost_usd=None,
            model=self._model,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_stub_version(
    template: str = "Directives: {global_directives}\nClusters:\n{clusters}\nSignals:\n{signals}",
) -> dict:
    return {
        "id": uuid4(),
        "template": template,
        "prompt_name": "decomposer",
        "version_number": 1,
    }


def _make_stub_project(
    tenant_id: UUID | None = None, global_directives: str = "Directives test"
) -> dict:
    return {
        "id": uuid4(),
        "tenant_id": tenant_id or uuid4(),
        "display_name": "Projet test",
        "global_directives": global_directives,
    }


def _make_clusters(n: int, signal_ids: list[UUID] | None = None) -> list[dict]:
    sids = signal_ids or [uuid4() for _ in range(n)]
    return [
        {
            "id": uuid4(),
            "name": f"Cluster {i}",
            "description": f"Desc cluster {i}",
            "signal_ids": [str(sids[i % len(sids)])],
        }
        for i in range(n)
    ]


def _make_signals(n: int) -> list[dict]:
    return [
        {
            "id": uuid4(),
            "type": "heuristique",
            "content": {"title": f"Signal {i}"},
        }
        for i in range(n)
    ]


def _make_valid_decomposer_response(signal_ids: list[UUID]) -> str:
    """Réponse JSON valide avec 3 sections et quelques documents."""
    return json.dumps(
        {
            "sections": {
                "Role": {
                    "documents": [
                        {
                            "name": "principe-autonomie",
                            "brief": "L'agent agit de façon autonome.",
                            "supporting_signals": [str(signal_ids[0])],
                        }
                    ]
                },
                "Missions": {
                    "documents": [
                        {
                            "name": "mission-analyse",
                            "brief": "Analyser les données.",
                            "supporting_signals": [str(signal_ids[0])],
                        },
                        {
                            "name": "mission-synthese",
                            "brief": "Synthétiser les résultats.",
                            "supporting_signals": [str(signal_ids[0])],
                        },
                    ]
                },
                "Skills": {"documents": []},
            }
        }
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_happy_path_inserts_3_plans_and_marks_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Happy path : 2 clusters, LLM retourne 3 sections → 3 INSERT document_plans,
    mark_done appelé avec plans_count et sections."""
    from role_builder.synthesis import decomposer

    signal_ids = [uuid4(), uuid4()]
    version = _make_stub_version()
    project = _make_stub_project()
    clusters = _make_clusters(2, signal_ids)
    signals = _make_signals(2)
    run_id = uuid4()
    valid_response = _make_valid_decomposer_response(signal_ids)

    stub_client = _StubClient(valid_response)
    inserted_plan_ids: list[UUID] = []
    mark_done_calls: list[dict] = []

    async def fake_get_system_default(name: str, *, pool: Any) -> dict:
        assert name == "decomposer"
        return version

    async def fake_get_by_id(project_id: UUID, *, pool: Any) -> dict:
        return project

    async def fake_list_clusters_by_project(project_id: UUID, *, pool: Any) -> list[dict]:
        return clusters

    async def fake_get_signals_by_ids(ids: list[UUID], *, pool: Any) -> list[dict]:
        return signals

    async def fake_create_run(**kwargs: Any) -> UUID:
        return run_id

    async def fake_mark_running(rid: UUID, *, pool: Any) -> None:
        pass

    async def fake_mark_done(rid: UUID, *, output: Any, **kwargs: Any) -> None:
        mark_done_calls.append({"run_id": rid, "output": output, **kwargs})

    async def fake_insert_document_plan(**kwargs: Any) -> UUID:
        pid = uuid4()
        inserted_plan_ids.append(pid)
        return pid

    monkeypatch.setattr(
        decomposer.prompts_helper, "get_system_default_version", fake_get_system_default
    )
    monkeypatch.setattr(decomposer.role_projects, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(
        decomposer.clusters_helper, "list_clusters_by_project", fake_list_clusters_by_project
    )
    monkeypatch.setattr(decomposer.signals_helper, "get_signals_by_ids", fake_get_signals_by_ids)
    monkeypatch.setattr(decomposer.runs, "create_run", fake_create_run)
    monkeypatch.setattr(decomposer.runs, "mark_running", fake_mark_running)
    monkeypatch.setattr(decomposer.runs, "mark_done", fake_mark_done)
    monkeypatch.setattr(
        decomposer.document_plans_helper, "insert_document_plan", fake_insert_document_plan
    )
    monkeypatch.setattr(decomposer, "get_agflow_client", lambda: stub_client)

    pool = _StubPool(_StubConn())
    result = await decomposer.run_decomposition(project["id"], pool=pool)

    assert result == run_id
    # 3 sections → 3 INSERTs (même Skills avec liste vide)
    assert len(inserted_plan_ids) == 3
    assert len(mark_done_calls) == 1
    output = json.loads(mark_done_calls[0]["output"])
    assert output["plans_count"] == 3
    assert "sections" in output
    assert len(stub_client.calls) == 1


async def test_no_clusters_raises_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pas de clusters → RuntimeError avant create_run."""
    from role_builder.synthesis import decomposer

    version = _make_stub_version()
    project = _make_stub_project()

    async def fake_get_system_default(name: str, *, pool: Any) -> dict:
        return version

    async def fake_get_by_id(project_id: UUID, *, pool: Any) -> dict:
        return project

    async def fake_list_clusters_by_project(project_id: UUID, *, pool: Any) -> list[dict]:
        return []

    create_run_called = False

    async def fake_create_run(**kwargs: Any) -> UUID:
        nonlocal create_run_called
        create_run_called = True
        return uuid4()

    monkeypatch.setattr(
        decomposer.prompts_helper, "get_system_default_version", fake_get_system_default
    )
    monkeypatch.setattr(decomposer.role_projects, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(
        decomposer.clusters_helper, "list_clusters_by_project", fake_list_clusters_by_project
    )
    monkeypatch.setattr(decomposer.runs, "create_run", fake_create_run)

    pool = _StubPool(_StubConn())
    with pytest.raises(RuntimeError, match="no clusters to decompose"):
        await decomposer.run_decomposition(project["id"], pool=pool)

    assert not create_run_called


async def test_invalid_section_in_llm_response_calls_cleanup_and_reraises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JSON avec section inconnue (ex: 'Habits') → ValidationError →
    delete_plans_by_run + mark_failed, exception re-raise."""
    from role_builder.synthesis import decomposer

    version = _make_stub_version()
    project = _make_stub_project()
    signal_ids = [uuid4()]
    clusters = _make_clusters(1, signal_ids)
    signals = _make_signals(1)
    run_id = uuid4()

    # 'Habits' n'est pas dans le Literal → ValidationError attendu
    bad_response = json.dumps(
        {
            "sections": {
                "Habits": {
                    "documents": [
                        {
                            "name": "mauvais-doc",
                            "brief": "Ne doit pas passer.",
                            "supporting_signals": [str(signal_ids[0])],
                        }
                    ]
                }
            }
        }
    )
    stub_client = _StubClient(bad_response)

    async def fake_get_system_default(name: str, *, pool: Any) -> dict:
        return version

    async def fake_get_by_id(project_id: UUID, *, pool: Any) -> dict:
        return project

    async def fake_list_clusters_by_project(project_id: UUID, *, pool: Any) -> list[dict]:
        return clusters

    async def fake_get_signals_by_ids(ids: list[UUID], *, pool: Any) -> list[dict]:
        return signals

    async def fake_create_run(**kwargs: Any) -> UUID:
        return run_id

    async def fake_mark_running(rid: UUID, *, pool: Any) -> None:
        pass

    call_order: list[str] = []

    async def fake_delete_plans_by_run(rid: UUID, *, pool: Any) -> int:
        call_order.append("delete_plans")
        return 0

    mark_failed_calls: list[dict] = []

    async def fake_mark_failed(rid: UUID, error: str, *, pool: Any) -> None:
        call_order.append("mark_failed")
        mark_failed_calls.append({"run_id": rid, "error": error})

    async def fake_mark_done(rid: UUID, **kwargs: Any) -> None:
        pytest.fail("mark_done NE DOIT PAS être appelé en cas d'échec")

    monkeypatch.setattr(
        decomposer.prompts_helper, "get_system_default_version", fake_get_system_default
    )
    monkeypatch.setattr(decomposer.role_projects, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(
        decomposer.clusters_helper, "list_clusters_by_project", fake_list_clusters_by_project
    )
    monkeypatch.setattr(decomposer.signals_helper, "get_signals_by_ids", fake_get_signals_by_ids)
    monkeypatch.setattr(decomposer.runs, "create_run", fake_create_run)
    monkeypatch.setattr(decomposer.runs, "mark_running", fake_mark_running)
    monkeypatch.setattr(decomposer.runs, "mark_failed", fake_mark_failed)
    monkeypatch.setattr(decomposer.runs, "mark_done", fake_mark_done)
    monkeypatch.setattr(
        decomposer.document_plans_helper, "delete_plans_by_run", fake_delete_plans_by_run
    )
    monkeypatch.setattr(decomposer, "get_agflow_client", lambda: stub_client)

    pool = _StubPool(_StubConn())
    with pytest.raises(ValueError):  # Pydantic ValidationError hérite de ValueError
        await decomposer.run_decomposition(project["id"], pool=pool)

    assert len(mark_failed_calls) == 1
    assert mark_failed_calls[0]["run_id"] == run_id
    assert call_order.index("delete_plans") < call_order.index("mark_failed")


async def test_instruction_override_added_to_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """instruction_override → message user ajouté dans la liste messages."""
    from role_builder.synthesis import decomposer

    signal_ids = [uuid4()]
    version = _make_stub_version()
    project = _make_stub_project()
    clusters = _make_clusters(1, signal_ids)
    signals = _make_signals(1)
    run_id = uuid4()
    valid_response = _make_valid_decomposer_response(signal_ids)
    stub_client = _StubClient(valid_response)

    async def fake_get_system_default(name: str, *, pool: Any) -> dict:
        return version

    async def fake_get_by_id(project_id: UUID, *, pool: Any) -> dict:
        return project

    async def fake_list_clusters_by_project(project_id: UUID, *, pool: Any) -> list[dict]:
        return clusters

    async def fake_get_signals_by_ids(ids: list[UUID], *, pool: Any) -> list[dict]:
        return signals

    async def fake_create_run(**kwargs: Any) -> UUID:
        return run_id

    async def fake_mark_running(rid: UUID, *, pool: Any) -> None:
        pass

    async def fake_mark_done(rid: UUID, **kwargs: Any) -> None:
        pass

    async def fake_insert_document_plan(**kwargs: Any) -> UUID:
        return uuid4()

    monkeypatch.setattr(
        decomposer.prompts_helper, "get_system_default_version", fake_get_system_default
    )
    monkeypatch.setattr(decomposer.role_projects, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(
        decomposer.clusters_helper, "list_clusters_by_project", fake_list_clusters_by_project
    )
    monkeypatch.setattr(decomposer.signals_helper, "get_signals_by_ids", fake_get_signals_by_ids)
    monkeypatch.setattr(decomposer.runs, "create_run", fake_create_run)
    monkeypatch.setattr(decomposer.runs, "mark_running", fake_mark_running)
    monkeypatch.setattr(decomposer.runs, "mark_done", fake_mark_done)
    monkeypatch.setattr(
        decomposer.document_plans_helper, "insert_document_plan", fake_insert_document_plan
    )
    monkeypatch.setattr(decomposer, "get_agflow_client", lambda: stub_client)

    pool = _StubPool(_StubConn())
    await decomposer.run_decomposition(
        project["id"],
        instruction_override="Priorise les Skills.",
        pool=pool,
    )

    assert len(stub_client.calls) == 1
    messages, _ = stub_client.calls[0]
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "Priorise les Skills."


async def test_cluster_run_id_uses_list_by_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Si cluster_run_id fourni → list_clusters_by_run appelé ;
    sinon → list_clusters_by_project."""
    from role_builder.synthesis import decomposer

    signal_ids = [uuid4()]
    version = _make_stub_version()
    project = _make_stub_project()
    clusters = _make_clusters(1, signal_ids)
    signals = _make_signals(1)
    run_id = uuid4()
    cluster_run_id = uuid4()
    valid_response = _make_valid_decomposer_response(signal_ids)
    stub_client = _StubClient(valid_response)

    list_by_run_called = False
    list_by_project_called = False

    async def fake_get_system_default(name: str, *, pool: Any) -> dict:
        return version

    async def fake_get_by_id(project_id: UUID, *, pool: Any) -> dict:
        return project

    async def fake_list_clusters_by_run(crun_id: UUID, *, pool: Any) -> list[dict]:
        nonlocal list_by_run_called
        list_by_run_called = True
        assert crun_id == cluster_run_id
        return clusters

    async def fake_list_clusters_by_project(project_id: UUID, *, pool: Any) -> list[dict]:
        nonlocal list_by_project_called
        list_by_project_called = True
        return clusters

    async def fake_get_signals_by_ids(ids: list[UUID], *, pool: Any) -> list[dict]:
        return signals

    async def fake_create_run(**kwargs: Any) -> UUID:
        return run_id

    async def fake_mark_running(rid: UUID, *, pool: Any) -> None:
        pass

    async def fake_mark_done(rid: UUID, **kwargs: Any) -> None:
        pass

    async def fake_insert_document_plan(**kwargs: Any) -> UUID:
        return uuid4()

    monkeypatch.setattr(
        decomposer.prompts_helper, "get_system_default_version", fake_get_system_default
    )
    monkeypatch.setattr(decomposer.role_projects, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(
        decomposer.clusters_helper, "list_clusters_by_run", fake_list_clusters_by_run
    )
    monkeypatch.setattr(
        decomposer.clusters_helper, "list_clusters_by_project", fake_list_clusters_by_project
    )
    monkeypatch.setattr(decomposer.signals_helper, "get_signals_by_ids", fake_get_signals_by_ids)
    monkeypatch.setattr(decomposer.runs, "create_run", fake_create_run)
    monkeypatch.setattr(decomposer.runs, "mark_running", fake_mark_running)
    monkeypatch.setattr(decomposer.runs, "mark_done", fake_mark_done)
    monkeypatch.setattr(
        decomposer.document_plans_helper, "insert_document_plan", fake_insert_document_plan
    )
    monkeypatch.setattr(decomposer, "get_agflow_client", lambda: stub_client)

    pool = _StubPool(_StubConn())

    # Avec cluster_run_id : list_by_run doit être appelé
    await decomposer.run_decomposition(project["id"], cluster_run_id=cluster_run_id, pool=pool)
    assert list_by_run_called is True
    assert list_by_project_called is False

    # Sans cluster_run_id : list_by_project doit être appelé
    list_by_run_called = False
    list_by_project_called = False
    await decomposer.run_decomposition(project["id"], pool=pool)
    assert list_by_run_called is False
    assert list_by_project_called is True
