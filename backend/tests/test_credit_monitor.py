"""Tests pour credit_monitor.poll_all_balances."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4


class _StubPool:
    """Pool sans connexion réelle — db_helpers monkeypatchés."""

    def acquire(self) -> Any:
        raise AssertionError("Pool.acquire ne doit pas être appelé")


class _StubSecretStore:
    """SecretStore stub : valeurs par secret_id."""

    def __init__(self, secrets: dict[UUID, str | None]) -> None:
        self._secrets = secrets

    async def read_secret_by_id(
        self, *, secret_id: UUID, user_id: UUID, pool: Any
    ) -> str | None:
        return self._secrets.get(secret_id)


def _make_key(
    *,
    secret_id: UUID | None = None,
    provider: str = "deepgram",
    monthly_cap_usd: float | None = None,
) -> dict[str, Any]:
    return {
        "id": uuid4(),
        "user_id": uuid4(),
        "provider": provider,
        "secret_id": secret_id if secret_id is not None else uuid4(),
        "monthly_cap_usd": monthly_cap_usd,
    }


# ---------------------------------------------------------------------------
# Test 1 — Happy path : 2 clés actives, balances normales
# ---------------------------------------------------------------------------


async def test_poll_all_balances_happy_path_two_keys(
    monkeypatch: Any,
    stubbed_env: None,
) -> None:
    """2 clés actives → update_key_balance appelé 2 fois, counters corrects."""
    from role_builder.db_helpers import transcription_keys as keys_helper
    from role_builder.services import credit_monitor, transcription_validator

    key1 = _make_key()
    key2 = _make_key()

    update_calls: list[dict] = []
    mark_exhausted_calls: list[Any] = []

    async def fake_list_active(*, pool: Any) -> list[dict]:
        return [key1, key2]

    async def fake_update_balance(
        key_id: Any, *, balance_usd: float, checked_at: Any, pool: Any
    ) -> None:
        update_calls.append({"key_id": key_id, "balance_usd": balance_usd})

    async def fake_mark_exhausted(key_id: Any, *, pool: Any) -> None:
        mark_exhausted_calls.append(key_id)

    async def fake_fetch_balance(provider: str, api_key: str) -> float | None:
        return 50.0 if api_key == "key1" else 100.0

    monkeypatch.setattr(keys_helper, "list_active_keys_for_balance_polling", fake_list_active)
    monkeypatch.setattr(keys_helper, "update_key_balance", fake_update_balance)
    monkeypatch.setattr(keys_helper, "mark_exhausted", fake_mark_exhausted)
    monkeypatch.setattr(transcription_validator, "fetch_balance", fake_fetch_balance)

    store = _StubSecretStore({key1["secret_id"]: "key1", key2["secret_id"]: "key2"})

    counters = await credit_monitor.poll_all_balances(pool=_StubPool(), secret_store=store)

    assert counters == {"polled": 2, "updated": 2, "exhausted": 0, "errors": 0}
    assert len(update_calls) == 2
    assert update_calls[0]["balance_usd"] == 50.0
    assert update_calls[1]["balance_usd"] == 100.0
    assert mark_exhausted_calls == []


# ---------------------------------------------------------------------------
# Test 2 — Balance 0 → mark_exhausted
# ---------------------------------------------------------------------------


async def test_poll_balance_zero_marks_exhausted(
    monkeypatch: Any,
    stubbed_env: None,
) -> None:
    """Balance 0 → update_key_balance + mark_exhausted, counters.exhausted=1."""
    from role_builder.db_helpers import transcription_keys as keys_helper
    from role_builder.services import credit_monitor, transcription_validator

    key = _make_key()
    update_calls: list[dict] = []
    mark_exhausted_calls: list[Any] = []

    async def fake_list_active(*, pool: Any) -> list[dict]:
        return [key]

    async def fake_update_balance(
        key_id: Any, *, balance_usd: float, checked_at: Any, pool: Any
    ) -> None:
        update_calls.append({"key_id": key_id, "balance_usd": balance_usd})

    async def fake_mark_exhausted(key_id: Any, *, pool: Any) -> None:
        mark_exhausted_calls.append(key_id)

    async def fake_fetch_balance(provider: str, api_key: str) -> float | None:
        return 0.0

    monkeypatch.setattr(keys_helper, "list_active_keys_for_balance_polling", fake_list_active)
    monkeypatch.setattr(keys_helper, "update_key_balance", fake_update_balance)
    monkeypatch.setattr(keys_helper, "mark_exhausted", fake_mark_exhausted)
    monkeypatch.setattr(transcription_validator, "fetch_balance", fake_fetch_balance)

    store = _StubSecretStore({key["secret_id"]: "mykey"})
    counters = await credit_monitor.poll_all_balances(pool=_StubPool(), secret_store=store)

    assert counters["exhausted"] == 1
    assert counters["updated"] == 1
    assert counters["errors"] == 0
    assert len(update_calls) == 1
    assert mark_exhausted_calls == [key["id"]]


# ---------------------------------------------------------------------------
# Test 3 — Secret inaccessible (supprimé ou disparu du wallet)
# ---------------------------------------------------------------------------


async def test_poll_secret_missing_counts_as_error(
    monkeypatch: Any,
    stubbed_env: None,
) -> None:
    """Secret irrésolvable → counters.errors=1, fetch_balance non appelé."""
    from role_builder.db_helpers import transcription_keys as keys_helper
    from role_builder.services import credit_monitor, transcription_validator

    key = _make_key()
    fetch_calls: list[Any] = []

    async def fake_list_active(*, pool: Any) -> list[dict]:
        return [key]

    async def fake_fetch_balance(provider: str, api_key: str) -> float | None:
        fetch_calls.append(api_key)
        return 50.0

    monkeypatch.setattr(keys_helper, "list_active_keys_for_balance_polling", fake_list_active)
    monkeypatch.setattr(transcription_validator, "fetch_balance", fake_fetch_balance)

    store = _StubSecretStore({key["secret_id"]: None})
    counters = await credit_monitor.poll_all_balances(pool=_StubPool(), secret_store=store)

    assert counters["errors"] == 1
    assert counters["polled"] == 1
    assert counters["updated"] == 0
    assert fetch_calls == []


# ---------------------------------------------------------------------------
# Test 3bis — Clé legacy sans secret_id → erreur, fetch non appelé
# ---------------------------------------------------------------------------


async def test_poll_key_without_secret_id_counts_as_error(
    monkeypatch: Any,
    stubbed_env: None,
) -> None:
    """Clé sans secret_id (legacy) → errors=1, fetch_balance non appelé."""
    from role_builder.db_helpers import transcription_keys as keys_helper
    from role_builder.services import credit_monitor, transcription_validator

    key = _make_key()
    key["secret_id"] = None
    fetch_calls: list[Any] = []

    async def fake_list_active(*, pool: Any) -> list[dict]:
        return [key]

    async def fake_fetch_balance(provider: str, api_key: str) -> float | None:
        fetch_calls.append(api_key)
        return 50.0

    monkeypatch.setattr(keys_helper, "list_active_keys_for_balance_polling", fake_list_active)
    monkeypatch.setattr(transcription_validator, "fetch_balance", fake_fetch_balance)

    store = _StubSecretStore({})
    counters = await credit_monitor.poll_all_balances(pool=_StubPool(), secret_store=store)

    assert counters["errors"] == 1
    assert fetch_calls == []


# ---------------------------------------------------------------------------
# Test 4 — fetch_balance retourne None (provider non supporté)
# ---------------------------------------------------------------------------


async def test_poll_fetch_balance_none_skips_update(
    monkeypatch: Any,
    stubbed_env: None,
) -> None:
    """fetch_balance retourne None → polled=1, updated=0, pas d'erreur."""
    from role_builder.db_helpers import transcription_keys as keys_helper
    from role_builder.services import credit_monitor, transcription_validator

    key = _make_key(provider="openai-whisper")
    update_calls: list[Any] = []

    async def fake_list_active(*, pool: Any) -> list[dict]:
        return [key]

    async def fake_update_balance(
        key_id: Any, *, balance_usd: float, checked_at: Any, pool: Any
    ) -> None:
        update_calls.append(key_id)

    async def fake_fetch_balance(provider: str, api_key: str) -> float | None:
        return None

    monkeypatch.setattr(keys_helper, "list_active_keys_for_balance_polling", fake_list_active)
    monkeypatch.setattr(keys_helper, "update_key_balance", fake_update_balance)
    monkeypatch.setattr(transcription_validator, "fetch_balance", fake_fetch_balance)

    store = _StubSecretStore({key["secret_id"]: "whisperkey"})
    counters = await credit_monitor.poll_all_balances(pool=_StubPool(), secret_store=store)

    assert counters["polled"] == 1
    assert counters["updated"] == 0
    assert counters["errors"] == 0
    assert update_calls == []


# ---------------------------------------------------------------------------
# Test 5 — Exception sur la première clé, deuxième clé OK
# ---------------------------------------------------------------------------


async def test_poll_exception_on_first_key_continues_second(
    monkeypatch: Any,
    stubbed_env: None,
) -> None:
    """Première clé lève une exception → errors=1 ; deuxième clé OK → updated=1."""
    from role_builder.db_helpers import transcription_keys as keys_helper
    from role_builder.services import credit_monitor, transcription_validator

    key1 = _make_key()
    key2 = _make_key()
    update_calls: list[Any] = []

    async def fake_list_active(*, pool: Any) -> list[dict]:
        return [key1, key2]

    async def fake_update_balance(
        key_id: Any, *, balance_usd: float, checked_at: Any, pool: Any
    ) -> None:
        update_calls.append(key_id)

    async def fake_fetch_balance(provider: str, api_key: str) -> float | None:
        if api_key == "boom":
            raise RuntimeError("réseau indisponible")
        return 75.0

    monkeypatch.setattr(keys_helper, "list_active_keys_for_balance_polling", fake_list_active)
    monkeypatch.setattr(keys_helper, "update_key_balance", fake_update_balance)
    monkeypatch.setattr(transcription_validator, "fetch_balance", fake_fetch_balance)

    store = _StubSecretStore({key1["secret_id"]: "boom", key2["secret_id"]: "fine"})
    counters = await credit_monitor.poll_all_balances(pool=_StubPool(), secret_store=store)

    assert counters["errors"] == 1
    assert counters["updated"] == 1
    assert counters["polled"] == 2


# ---------------------------------------------------------------------------
# Test 6 — Low balance → update appelé, mark_exhausted non appelé
# ---------------------------------------------------------------------------


async def test_poll_low_balance_updates_without_exhausting(
    monkeypatch: Any,
    stubbed_env: None,
) -> None:
    """Balance 5$ avec cap 100$ (5% < 20%) → update appelé, mark_exhausted non."""
    from role_builder.db_helpers import transcription_keys as keys_helper
    from role_builder.services import credit_monitor, transcription_validator

    key = _make_key(monthly_cap_usd=100.0)
    update_calls: list[Any] = []
    mark_exhausted_calls: list[Any] = []

    async def fake_list_active(*, pool: Any) -> list[dict]:
        return [key]

    async def fake_update_balance(
        key_id: Any, *, balance_usd: float, checked_at: Any, pool: Any
    ) -> None:
        update_calls.append({"key_id": key_id, "balance_usd": balance_usd})

    async def fake_mark_exhausted(key_id: Any, *, pool: Any) -> None:
        mark_exhausted_calls.append(key_id)

    async def fake_fetch_balance(provider: str, api_key: str) -> float | None:
        return 5.0  # 5% of 100$ → below 20% threshold

    monkeypatch.setattr(keys_helper, "list_active_keys_for_balance_polling", fake_list_active)
    monkeypatch.setattr(keys_helper, "update_key_balance", fake_update_balance)
    monkeypatch.setattr(keys_helper, "mark_exhausted", fake_mark_exhausted)
    monkeypatch.setattr(transcription_validator, "fetch_balance", fake_fetch_balance)

    store = _StubSecretStore({key["secret_id"]: "lowkey"})
    counters = await credit_monitor.poll_all_balances(pool=_StubPool(), secret_store=store)

    assert counters["updated"] == 1
    assert counters["exhausted"] == 0
    assert len(update_calls) == 1
    assert update_calls[0]["balance_usd"] == 5.0
    assert mark_exhausted_calls == []
