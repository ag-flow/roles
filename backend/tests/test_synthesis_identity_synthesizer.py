"""Tests TDD pour synthesis/identity_synthesizer.py — synthesize_identity."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from role_builder.services.agflow_client import ChatResult

# ---------------------------------------------------------------------------
# Stubs asyncpg pool (minimaliste, non utilisé directement dans ces tests)
# ---------------------------------------------------------------------------


class _StubConn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, tuple[Any, ...]]] = []
        self.fetchval_return: Any = None
        self.fetchrow_return: Any = None
        self.fetch_return: list[Any] = []
        self.execute_return: str = "UPDATE 1"

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
    def __init__(
        self, content: str = "# Identity\n\nJe suis un agent.", model: str = "mistral-test"
    ) -> None:
        self._content = content
        self._model = model
        self.calls: list[tuple[list[dict], dict | None]] = []

    async def invoke_chat(
        self, messages: list[dict], *, response_format: dict | None = None
    ) -> ChatResult:
        self.calls.append((messages, response_format))
        return ChatResult(
            content=self._content,
            tokens_input=15,
            tokens_output=30,
            cost_usd=None,
            model=self._model,
        )


# ---------------------------------------------------------------------------
# Helpers builders
# ---------------------------------------------------------------------------


def _make_version(
    template: str = (
        "Rôle: {display_name}\nDesc: {description}\n"
        "Directives: {global_directives}\nDocuments:\n{documents}"
    ),
) -> dict:
    return {
        "id": uuid4(),
        "template": template,
        "prompt_name": "identity_synthesizer",
        "version_number": 1,
    }


def _make_project(
    display_name: str = "Agent Finance",
    description: str = "Agent financier.",
    global_directives: str = "Sois concis.",
    tenant_id: UUID | None = None,
) -> dict:
    return {
        "id": uuid4(),
        "tenant_id": tenant_id or uuid4(),
        "display_name": display_name,
        "description": description,
        "global_directives": global_directives,
    }


def _make_docs(sections: list[str] | None = None) -> list[dict]:
    """Génère une liste de documents courants pour les sections données."""
    if sections is None:
        sections = ["Role", "Role", "Missions", "Missions", "Skills"]
    docs = []
    for i, section in enumerate(sections):
        docs.append(
            {
                "id": uuid4(),
                "section": section,
                "name": f"doc-{section.lower()}-{i}",
                "content": f"Contenu du document {i} pour section {section}.",
            }
        )
    return docs


# ---------------------------------------------------------------------------
# Patch helper
# ---------------------------------------------------------------------------


def _patch_identity_synthesizer(
    monkeypatch: pytest.MonkeyPatch,
    *,
    version: dict,
    project: dict,
    docs: list[dict],
    run_id: UUID,
    stub_client: _StubClient,
    mark_done_calls: list[dict] | None = None,
    mark_failed_calls: list[dict] | None = None,
    update_identity_calls: list[dict] | None = None,
) -> None:
    """Monkeypatche toutes les dépendances d'identity_synthesizer."""
    from role_builder.synthesis import identity_synthesizer

    if mark_done_calls is None:
        mark_done_calls = []
    if mark_failed_calls is None:
        mark_failed_calls = []
    if update_identity_calls is None:
        update_identity_calls = []

    async def fake_get_system_default(name: str, *, pool: Any) -> dict:
        return version

    async def fake_get_by_id(pid: UUID, *, pool: Any) -> dict:
        return project

    async def fake_list_current_by_project(pid: UUID, *, pool: Any) -> list[dict]:
        return docs

    async def fake_create_run(**kwargs: Any) -> UUID:
        return run_id

    async def fake_mark_running(rid: UUID, *, pool: Any) -> None:
        pass

    async def fake_mark_done(rid: UUID, *, output: Any, **kwargs: Any) -> None:
        mark_done_calls.append({"run_id": rid, **kwargs})

    async def fake_mark_failed(rid: UUID, error: str, *, pool: Any) -> None:
        mark_failed_calls.append({"run_id": rid, "error": error})

    async def fake_update_identity(pid: UUID, identity: str, *, pool: Any) -> None:
        update_identity_calls.append({"role_project_id": pid, "identity": identity})

    monkeypatch.setattr(
        identity_synthesizer.prompts_helper, "get_system_default_version", fake_get_system_default
    )
    monkeypatch.setattr(identity_synthesizer.role_projects, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(
        identity_synthesizer.role_documents_helper,
        "list_current_by_project",
        fake_list_current_by_project,
    )
    monkeypatch.setattr(identity_synthesizer.runs, "create_run", fake_create_run)
    monkeypatch.setattr(identity_synthesizer.runs, "mark_running", fake_mark_running)
    monkeypatch.setattr(identity_synthesizer.runs, "mark_done", fake_mark_done)
    monkeypatch.setattr(identity_synthesizer.runs, "mark_failed", fake_mark_failed)
    monkeypatch.setattr(identity_synthesizer.role_projects, "update_identity", fake_update_identity)
    monkeypatch.setattr(identity_synthesizer, "get_agflow_client", lambda: stub_client)


# ---------------------------------------------------------------------------
# F1.1 — Happy path
# ---------------------------------------------------------------------------


async def test_synthesize_identity_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """5 docs current (Role/Missions/Skills) → update_identity appelé, mark_done appelé, run_id retourné."""
    from role_builder.synthesis import identity_synthesizer

    project = _make_project()
    version = _make_version()
    docs = _make_docs(["Role", "Role", "Missions", "Missions", "Skills"])
    run_id = uuid4()
    stub_client = _StubClient("Je suis un agent financier spécialisé.")
    mark_done_calls: list[dict] = []
    update_identity_calls: list[dict] = []

    _patch_identity_synthesizer(
        monkeypatch,
        version=version,
        project=project,
        docs=docs,
        run_id=run_id,
        stub_client=stub_client,
        mark_done_calls=mark_done_calls,
        update_identity_calls=update_identity_calls,
    )

    pool = _StubPool(_StubConn())
    result = await identity_synthesizer.synthesize_identity(project["id"], pool=pool)

    assert result == run_id
    # update_identity appelé avec le markdown retourné
    assert len(update_identity_calls) == 1
    assert update_identity_calls[0]["role_project_id"] == project["id"]
    assert update_identity_calls[0]["identity"] == "Je suis un agent financier spécialisé."
    # mark_done appelé
    assert len(mark_done_calls) == 1
    assert mark_done_calls[0]["run_id"] == run_id
    # response_format absent (markdown libre)
    messages, response_format = stub_client.calls[0]
    assert response_format is None
    # system message contient le display_name
    system_content = messages[0]["content"]
    assert "Agent Finance" in system_content


# ---------------------------------------------------------------------------
# F1.2 — Aucun doc current → RuntimeError avant create_run
# ---------------------------------------------------------------------------


async def test_synthesize_identity_no_current_docs_raises_before_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """list_current_by_project retourne [] → RuntimeError, aucun create_run ni invoke_chat."""
    from role_builder.synthesis import identity_synthesizer

    project = _make_project()
    version = _make_version()
    run_id = uuid4()
    stub_client = _StubClient()
    create_run_calls: list[UUID] = []

    async def fake_get_system_default(name: str, *, pool: Any) -> dict:
        return version

    async def fake_get_by_id(pid: UUID, *, pool: Any) -> dict:
        return project

    async def fake_list_current_empty(pid: UUID, *, pool: Any) -> list[dict]:
        return []

    async def fake_create_run(**kwargs: Any) -> UUID:
        create_run_calls.append(run_id)
        return run_id

    monkeypatch.setattr(
        identity_synthesizer.prompts_helper, "get_system_default_version", fake_get_system_default
    )
    monkeypatch.setattr(identity_synthesizer.role_projects, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(
        identity_synthesizer.role_documents_helper,
        "list_current_by_project",
        fake_list_current_empty,
    )
    monkeypatch.setattr(identity_synthesizer.runs, "create_run", fake_create_run)
    monkeypatch.setattr(identity_synthesizer, "get_agflow_client", lambda: stub_client)

    pool = _StubPool(_StubConn())
    with pytest.raises(RuntimeError, match="promote at least one document"):
        await identity_synthesizer.synthesize_identity(project["id"], pool=pool)

    assert len(create_run_calls) == 0
    assert len(stub_client.calls) == 0


# ---------------------------------------------------------------------------
# F1.3 — Documents groupés par section dans le bon ordre
# ---------------------------------------------------------------------------


async def test_synthesize_identity_documents_grouped_by_section(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prompt formaté contient ## Role, ## Missions, ## Skills dans le bon ordre."""
    from role_builder.synthesis import identity_synthesizer

    project = _make_project()
    # Template simple qui passe les documents tels quels
    version = _make_version(
        template="{display_name}\n{description}\n{global_directives}\n{documents}"
    )
    docs = _make_docs(["Skills", "Role", "Missions", "Role", "Skills"])
    run_id = uuid4()
    stub_client = _StubClient()
    captured_messages: list[list[dict]] = []

    async def fake_invoke_chat(
        messages: list[dict], *, response_format: dict | None = None
    ) -> ChatResult:
        captured_messages.append(messages)
        return ChatResult(
            content="identity", tokens_input=10, tokens_output=5, cost_usd=None, model="m"
        )

    _patch_identity_synthesizer(
        monkeypatch,
        version=version,
        project=project,
        docs=docs,
        run_id=run_id,
        stub_client=stub_client,
    )
    # Override invoke_chat pour capturer
    monkeypatch.setattr(stub_client, "invoke_chat", fake_invoke_chat)

    pool = _StubPool(_StubConn())
    await identity_synthesizer.synthesize_identity(project["id"], pool=pool)

    assert len(captured_messages) == 1
    system_content = captured_messages[0][0]["content"]
    # Les 3 sections présentes
    assert "## Role" in system_content
    assert "## Missions" in system_content
    assert "## Skills" in system_content
    # Ordre : Role avant Missions avant Skills
    pos_role = system_content.index("## Role")
    pos_missions = system_content.index("## Missions")
    pos_skills = system_content.index("## Skills")
    assert pos_role < pos_missions < pos_skills


# ---------------------------------------------------------------------------
# F1.4 — invoke_chat échoue → mark_failed + raise, pas de cleanup spécifique
# ---------------------------------------------------------------------------


async def test_synthesize_identity_invoke_chat_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """invoke_chat échoue → mark_failed + raise (pas de cleanup docs)."""
    import httpx

    from role_builder.synthesis import identity_synthesizer

    project = _make_project()
    version = _make_version()
    docs = _make_docs(["Role", "Missions"])
    run_id = uuid4()
    mark_failed_calls: list[dict] = []
    update_identity_calls: list[dict] = []

    class _FailingClient:
        async def invoke_chat(
            self, messages: list[dict], *, response_format: dict | None = None
        ) -> ChatResult:
            raise httpx.HTTPError("LLM unreachable")

    _patch_identity_synthesizer(
        monkeypatch,
        version=version,
        project=project,
        docs=docs,
        run_id=run_id,
        stub_client=_FailingClient(),  # type: ignore[arg-type]
        mark_failed_calls=mark_failed_calls,
        update_identity_calls=update_identity_calls,
    )

    pool = _StubPool(_StubConn())
    with pytest.raises(httpx.HTTPError):
        await identity_synthesizer.synthesize_identity(project["id"], pool=pool)

    assert len(mark_failed_calls) == 1
    assert mark_failed_calls[0]["run_id"] == run_id
    # update_identity pas appelé (invoke_chat a échoué avant)
    assert len(update_identity_calls) == 0
