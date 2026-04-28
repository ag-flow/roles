"""Tests pour RoleBuilderScheduler."""

from __future__ import annotations

from typing import Any

import pytest


class _FakeAsyncIOScheduler:
    """Stub AsyncIOScheduler qui track add_job / start / shutdown."""

    def __init__(self) -> None:
        self._jobs: dict[str, Any] = {}
        self._running = False

    def add_job(self, func: Any, trigger: Any, *, id: str, replace_existing: bool = False) -> None:
        self._jobs[id] = {"func": func, "trigger": trigger}

    def start(self) -> None:
        self._running = True

    def get_jobs(self) -> list[Any]:
        return [type("J", (), {"id": jid})() for jid in self._jobs]

    def shutdown(self, wait: bool = False) -> None:
        self._running = False


class _StubPool:
    pass


# ---------------------------------------------------------------------------
# Test 1 — Instanciation sans start
# ---------------------------------------------------------------------------


def test_scheduler_instantiation(monkeypatch: pytest.MonkeyPatch, stubbed_env: None) -> None:
    """RoleBuilderScheduler(pool=...) ne plante pas, _started=False initialement."""
    monkeypatch.setattr(
        "role_builder.services.scheduler.AsyncIOScheduler",
        _FakeAsyncIOScheduler,
    )
    from role_builder.services.scheduler import RoleBuilderScheduler

    rbs = RoleBuilderScheduler(pool=_StubPool())
    assert rbs._started is False


# ---------------------------------------------------------------------------
# Test 2 — start() schedule 3 jobs
# ---------------------------------------------------------------------------


def test_scheduler_start_schedules_three_jobs(
    monkeypatch: pytest.MonkeyPatch, stubbed_env: None
) -> None:
    """Après start(), 3 jobs enregistrés avec les ids attendus."""
    monkeypatch.setattr(
        "role_builder.services.scheduler.AsyncIOScheduler",
        _FakeAsyncIOScheduler,
    )
    from role_builder.services.scheduler import RoleBuilderScheduler

    rbs = RoleBuilderScheduler(pool=_StubPool())
    rbs.start()

    jobs = rbs.scheduler.get_jobs()
    job_ids = {j.id for j in jobs}
    assert job_ids == {"poll_credit_balances", "reset_monthly_spend", "cleanup_revoked_secrets"}
    assert rbs._started is True


# ---------------------------------------------------------------------------
# Test 3 — start() idempotent
# ---------------------------------------------------------------------------


def test_scheduler_start_idempotent(monkeypatch: pytest.MonkeyPatch, stubbed_env: None) -> None:
    """Deux appels start() → toujours 3 jobs (pas 6)."""
    monkeypatch.setattr(
        "role_builder.services.scheduler.AsyncIOScheduler",
        _FakeAsyncIOScheduler,
    )
    from role_builder.services.scheduler import RoleBuilderScheduler

    rbs = RoleBuilderScheduler(pool=_StubPool())
    rbs.start()
    rbs.start()  # deuxième appel — no-op

    jobs = rbs.scheduler.get_jobs()
    assert len(jobs) == 3


# ---------------------------------------------------------------------------
# Test 4 — shutdown() après start
# ---------------------------------------------------------------------------


async def test_scheduler_shutdown_after_start(
    monkeypatch: pytest.MonkeyPatch, stubbed_env: None
) -> None:
    """shutdown() après start() ne lève pas, _started=False."""
    monkeypatch.setattr(
        "role_builder.services.scheduler.AsyncIOScheduler",
        _FakeAsyncIOScheduler,
    )
    from role_builder.services.scheduler import RoleBuilderScheduler

    rbs = RoleBuilderScheduler(pool=_StubPool())
    rbs.start()
    assert rbs._started is True

    await rbs.shutdown()
    assert rbs._started is False


# ---------------------------------------------------------------------------
# Test 5 — shutdown() sans start (no-op)
# ---------------------------------------------------------------------------


async def test_scheduler_shutdown_without_start(
    monkeypatch: pytest.MonkeyPatch, stubbed_env: None
) -> None:
    """shutdown() sans start() ne lève pas (no-op)."""
    monkeypatch.setattr(
        "role_builder.services.scheduler.AsyncIOScheduler",
        _FakeAsyncIOScheduler,
    )
    from role_builder.services.scheduler import RoleBuilderScheduler

    rbs = RoleBuilderScheduler(pool=_StubPool())
    # pas de start()
    await rbs.shutdown()  # ne doit pas lever
    assert rbs._started is False


# ---------------------------------------------------------------------------
# Test 6 — _reset_monthly_spend appelle reset_monthly_spend_all
# ---------------------------------------------------------------------------


async def test_scheduler_reset_monthly_spend_calls_helper(
    monkeypatch: pytest.MonkeyPatch, stubbed_env: None
) -> None:
    """_reset_monthly_spend() → reset_monthly_spend_all(pool=...) appelé."""
    monkeypatch.setattr(
        "role_builder.services.scheduler.AsyncIOScheduler",
        _FakeAsyncIOScheduler,
    )
    from role_builder.db_helpers import transcription_keys as keys_helper
    from role_builder.services.scheduler import RoleBuilderScheduler

    reset_calls: list[Any] = []

    async def fake_reset(*, pool: Any) -> int:
        reset_calls.append(pool)
        return 3

    monkeypatch.setattr(keys_helper, "reset_monthly_spend_all", fake_reset)

    pool = _StubPool()
    rbs = RoleBuilderScheduler(pool=pool)
    await rbs._reset_monthly_spend()

    assert len(reset_calls) == 1
    assert reset_calls[0] is pool
