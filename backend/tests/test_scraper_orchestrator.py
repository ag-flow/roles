"""Tests for services.scraper_orchestrator — process_one_job + run_loop."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest


@pytest.fixture()
def calls() -> dict[str, list[Any]]:
    return {
        "mark_processing": [],
        "mark_done": [],
        "mark_failed": [],
        "get_source": [],
        "handle_event": [],
        "run_container": [],
    }


@pytest.fixture()
def patched(monkeypatch: pytest.MonkeyPatch, calls: dict[str, list[Any]]) -> Any:
    """Patch out db_helpers + docker_runner + handle_scraper_event."""
    from role_builder.db_helpers import scraping_jobs as sj
    from role_builder.db_helpers import sources as sm
    from role_builder.services import event_handlers, scraper_orchestrator

    async def fake_mark_processing(job_id: Any, **kw: Any) -> None:
        calls["mark_processing"].append(job_id)

    async def fake_mark_done(job_id: Any, **kw: Any) -> None:
        calls["mark_done"].append(job_id)

    async def fake_mark_failed(job_id: Any, error: str, **kw: Any) -> None:
        calls["mark_failed"].append((job_id, error))

    async def fake_get_source(source_id: Any, **kw: Any) -> dict[str, Any]:
        calls["get_source"].append(source_id)
        return {
            "id": source_id,
            "platform": "youtube",
            "url": "https://www.youtube.com/@example",
            "role_project_id": uuid4(),
        }

    async def fake_handle_event(event: dict[str, Any], job: dict[str, Any], **kw: Any) -> None:
        calls["handle_event"].append((event, job))

    monkeypatch.setattr(sj, "mark_job_processing", fake_mark_processing)
    monkeypatch.setattr(sj, "mark_job_done", fake_mark_done)
    monkeypatch.setattr(sj, "mark_job_failed", fake_mark_failed)
    monkeypatch.setattr(sm, "get_source", fake_get_source)
    monkeypatch.setattr(event_handlers, "handle_scraper_event", fake_handle_event)
    monkeypatch.setattr(scraper_orchestrator, "handle_scraper_event", fake_handle_event)
    return calls


def _make_runner(events: list[dict[str, Any]]) -> Any:
    """Return an async generator factory yielding the given events."""

    async def runner(image: str, env: dict[str, str], stdin_payload: dict[str, Any], **kw: Any):
        runner.last_image = image  # type: ignore[attr-defined]
        runner.last_env = env  # type: ignore[attr-defined]
        runner.last_payload = stdin_payload  # type: ignore[attr-defined]
        for ev in events:
            yield ev

    return runner


async def test_process_one_job_discover_runs_runner_and_marks_done(
    patched: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """process_one_job builds payload, drives events through handler, marks done on rc=0."""
    from role_builder.services import scraper_orchestrator

    runner = _make_runner(
        [
            {"type": "started", "task_id": "t1"},
            {"type": "discovered", "total": 1, "items": [{"id": "v1"}]},
            {"type": "complete", "downloaded": 1},
            {"type": "_exit", "returncode": 0},
        ]
    )
    monkeypatch.setattr(scraper_orchestrator, "run_container", runner)

    job_id = uuid4()
    source_id = uuid4()
    tenant_id = uuid4()
    job = {
        "id": job_id,
        "source_id": source_id,
        "source_item_id": None,
        "tenant_id": tenant_id,
        "command": "discover",
        "credentials_id": None,
    }

    orch = scraper_orchestrator.ScraperOrchestrator(pool=object(), worker_id="w-1")
    await orch.process_one_job(job)

    # Lifecycle: marked processing once, done once, never failed
    assert patched["mark_processing"] == [job_id]
    assert patched["mark_done"] == [job_id]
    assert patched["mark_failed"] == []
    # Source fetched
    assert patched["get_source"] == [source_id]
    # Events dispatched: started, discovered, complete (the _exit may or may not be
    # forwarded — implementation choice, but must not crash)
    handler_event_types = [c[0]["type"] for c in patched["handle_event"]]
    assert "started" in handler_event_types
    assert "discovered" in handler_event_types
    assert "complete" in handler_event_types

    # Runner received correct image and stdin payload
    assert runner.last_image == "agflow-scraper-youtube:latest"  # type: ignore[attr-defined]
    payload = runner.last_payload  # type: ignore[attr-defined]
    assert payload["command"] == "discover"
    assert payload["url"] == "https://www.youtube.com/@example"
    assert payload["task_id"] == str(job_id)
    assert payload["output"]["type"] == "minio"


async def test_process_one_job_marks_failed_on_nonzero_returncode(
    patched: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-zero returncode marks the job failed."""
    from role_builder.services import scraper_orchestrator

    runner = _make_runner(
        [
            {"type": "started", "task_id": "t2"},
            {"type": "_exit", "returncode": 2},
        ]
    )
    monkeypatch.setattr(scraper_orchestrator, "run_container", runner)

    job_id = uuid4()
    job = {
        "id": job_id,
        "source_id": uuid4(),
        "source_item_id": None,
        "tenant_id": uuid4(),
        "command": "discover",
        "credentials_id": None,
    }
    orch = scraper_orchestrator.ScraperOrchestrator(pool=object(), worker_id="w-1")
    await orch.process_one_job(job)

    assert patched["mark_done"] == []
    assert len(patched["mark_failed"]) == 1
    failed_job_id, error_msg = patched["mark_failed"][0]
    assert failed_job_id == job_id
    assert "2" in error_msg


async def test_process_one_job_includes_cookies_in_env_when_set(
    patched: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If cookies are set for the platform, they are passed in env to the runner."""
    from role_builder.config import settings as _settings
    from role_builder.services import scraper_orchestrator

    monkeypatch.setattr(_settings, "youtube_cookies_b64", "b64-cookies", raising=False)

    runner = _make_runner([{"type": "_exit", "returncode": 0}])
    monkeypatch.setattr(scraper_orchestrator, "run_container", runner)

    job = {
        "id": uuid4(),
        "source_id": uuid4(),
        "source_item_id": None,
        "tenant_id": uuid4(),
        "command": "download",
        "credentials_id": None,
    }
    orch = scraper_orchestrator.ScraperOrchestrator(pool=object(), worker_id="w-1")
    await orch.process_one_job(job)

    env = runner.last_env  # type: ignore[attr-defined]
    assert env.get("YOUTUBE_COOKIES_B64") == "b64-cookies"
    assert "MINIO_ENDPOINT" in env


def test_build_payload_prefix_uses_role_project_id_when_present() -> None:
    """Source V1 (role_project_id renseigné) : comportement inchangé."""
    from role_builder.services.scraper_orchestrator import ScraperOrchestrator

    orch = ScraperOrchestrator(pool=object())
    role_project_id = uuid4()
    source_id = uuid4()
    tenant_id = uuid4()
    job = {"id": uuid4(), "tenant_id": tenant_id, "command": "discover"}
    source = {"id": source_id, "url": "https://x", "role_project_id": role_project_id}

    payload = orch._build_payload(job, source)

    assert payload["output"]["prefix"] == f"{tenant_id}/{role_project_id}/{source_id}/"


def test_build_payload_prefix_avoids_none_literal_when_role_project_id_null() -> None:
    """Source V2 (façade MCP, role_project_id NULL) : pas de littéral 'None' dans le prefix MinIO."""
    from role_builder.services.scraper_orchestrator import ScraperOrchestrator

    orch = ScraperOrchestrator(pool=object())
    source_id = uuid4()
    tenant_id = uuid4()
    job = {"id": uuid4(), "tenant_id": tenant_id, "command": "discover"}
    source = {"id": source_id, "url": "https://x", "role_project_id": None}

    payload = orch._build_payload(job, source)

    assert "None" not in payload["output"]["prefix"]
    assert payload["output"]["prefix"] == f"{tenant_id}/v2/{source_id}/"
