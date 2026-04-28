"""Tests for services.credit_basculer — bascule sur clé exhausted."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest


async def test_handle_key_exhausted_stops_workers_then_reassigns_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """handle_key_exhausted : 1. stop workers via manager  2. reassign jobs to shared."""
    from role_builder.db_helpers import transcription_jobs as tj
    from role_builder.services import credit_basculer

    key_id = uuid4()
    user_id = uuid4()
    pool = object()

    call_log: list[str] = []
    stop_args: dict[str, Any] = {}
    reassign_args: dict[str, Any] = {}

    class FakeManager:
        async def stop_workers_for_key(self, kid: UUID) -> int:
            call_log.append("stop")
            stop_args["key_id"] = kid
            return 3

    async def fake_reassign(user_pool_id: str, *, pool: Any) -> int:
        call_log.append("reassign")
        reassign_args["user_pool_id"] = user_pool_id
        reassign_args["pool"] = pool
        return 5

    monkeypatch.setattr(tj, "reassign_pending_to_shared", fake_reassign)

    await credit_basculer.handle_key_exhausted(
        key_id=key_id, user_id=user_id, pool=pool, manager=FakeManager()
    )

    # Stop puis reassign, dans cet ordre
    assert call_log == ["stop", "reassign"]
    assert stop_args["key_id"] == key_id
    assert reassign_args["user_pool_id"] == f"user_{user_id}"
    assert reassign_args["pool"] is pool


async def test_handle_key_exhausted_propagates_manager_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si manager.stop_workers_for_key lève, reassign n'est PAS appelé."""
    from role_builder.db_helpers import transcription_jobs as tj
    from role_builder.services import credit_basculer

    key_id = uuid4()
    user_id = uuid4()
    pool = object()

    class FailingManager:
        async def stop_workers_for_key(self, _: UUID) -> int:
            raise RuntimeError("docker daemon dead")

    reassign_called = False

    async def fake_reassign(*_: Any, **__: Any) -> int:
        nonlocal reassign_called
        reassign_called = True
        return 0

    monkeypatch.setattr(tj, "reassign_pending_to_shared", fake_reassign)

    with pytest.raises(RuntimeError, match="docker daemon dead"):
        await credit_basculer.handle_key_exhausted(
            key_id=key_id, user_id=user_id, pool=pool, manager=FailingManager()
        )
    assert reassign_called is False
