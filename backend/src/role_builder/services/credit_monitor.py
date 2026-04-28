"""Polling périodique des balances de crédit pour les providers
qui exposent une API balance (Deepgram principalement)."""

from __future__ import annotations

import datetime as dt
from typing import Any

import asyncpg
import structlog

from role_builder.db_helpers import transcription_keys as keys_helper
from role_builder.services import transcription_validator
from role_builder.services.openbao_client import OpenBaoClient

log = structlog.get_logger(__name__)

# Seuil de balance "low" : 20% du cap mensuel, ou 20$ si pas de cap.
_LOW_BALANCE_PCT_OF_CAP = 0.20
_LOW_BALANCE_DEFAULT_USD = 20.0


def _is_low_balance(balance: float, monthly_cap_usd: float | None) -> bool:
    threshold = (
        monthly_cap_usd * _LOW_BALANCE_PCT_OF_CAP
        if monthly_cap_usd is not None and monthly_cap_usd > 0
        else _LOW_BALANCE_DEFAULT_USD
    )
    return balance <= threshold


async def poll_all_balances(
    *,
    pool: asyncpg.Pool,
    openbao: OpenBaoClient | None = None,
) -> dict[str, int]:
    """Poll les balances des clés actives.
    Retourne {polled, updated, exhausted, errors}.

    Pour chaque clé :
    - Get api_key from OpenBao
    - fetch_balance(provider, api_key)
    - Si balance is None → skip (provider sans support)
    - Sinon update_key_balance + check thresholds :
      - balance == 0 → mark_exhausted, log warning
      - low balance → log warning (pas de side-effect DB MVP)
    """
    keys: list[dict[str, Any]] = await keys_helper.list_active_keys_for_balance_polling(pool=pool)
    counters = {"polled": 0, "updated": 0, "exhausted": 0, "errors": 0}

    own_openbao = openbao is None
    if openbao is None:
        openbao = OpenBaoClient()

    try:
        for key in keys:
            counters["polled"] += 1
            try:
                secret = await openbao.get(key["openbao_path"])
                if secret is None:
                    log.warning("credit_monitor.secret_missing", key_id=str(key["id"]))
                    counters["errors"] += 1
                    continue
                api_key = str(secret.get("api_key", ""))
                if not api_key:
                    log.warning("credit_monitor.empty_api_key", key_id=str(key["id"]))
                    counters["errors"] += 1
                    continue

                balance = await transcription_validator.fetch_balance(key["provider"], api_key)
                if balance is None:
                    continue

                now = dt.datetime.now(dt.UTC)
                await keys_helper.update_key_balance(
                    key["id"],
                    balance_usd=balance,
                    checked_at=now,
                    pool=pool,
                )
                counters["updated"] += 1

                if balance <= 0:
                    await keys_helper.mark_exhausted(key["id"], pool=pool)
                    counters["exhausted"] += 1
                    log.warning(
                        "credit_monitor.balance_exhausted",
                        key_id=str(key["id"]),
                        provider=key["provider"],
                    )
                elif _is_low_balance(balance, key.get("monthly_cap_usd")):
                    log.warning(
                        "credit_monitor.balance_low",
                        key_id=str(key["id"]),
                        provider=key["provider"],
                        balance_usd=balance,
                        monthly_cap_usd=key.get("monthly_cap_usd"),
                    )
            except Exception:
                counters["errors"] += 1
                log.exception("credit_monitor.poll_failed", key_id=str(key["id"]))
    finally:
        if own_openbao:
            await openbao.aclose()

    log.info("credit_monitor.poll_completed", **counters)
    return counters
