"""Validation des clés API des providers de transcription.

Effectue un appel trivial à l'API de chaque provider pour vérifier
que la clé fonctionne. Pour Deepgram, récupère aussi le solde.
"""

from __future__ import annotations

from typing import Any, Final

import httpx
import structlog

log = structlog.get_logger(__name__)

PROVIDER_CONFIG: Final[dict[str, dict[str, str]]] = {
    "openai-whisper": {
        "url": "https://api.openai.com/v1/models",
        "auth_template": "Bearer {key}",
    },
    "deepgram": {
        "url": "https://api.deepgram.com/v1/projects",
        "auth_template": "Token {key}",
    },
    "assemblyai": {
        "url": "https://api.assemblyai.com/v2/transcript?limit=1",
        "auth_template": "{key}",
    },
    "speechmatics": {
        "url": "https://asr.api.speechmatics.com/v2/jobs",
        "auth_template": "Bearer {key}",
    },
}

_TIMEOUT = 10.0


async def validate_transcription_key(provider: str, api_key: str) -> dict[str, Any]:
    """Appel API trivial pour vérifier que la clé fonctionne.

    Retourne {valid: bool, error: str | None, balance_usd: float | None}.

    balance_usd uniquement renseigné pour Deepgram (autres ne l'exposent pas
    trivialement). Pour Deepgram on tente fetch_balance après validation OK.
    """
    config = PROVIDER_CONFIG.get(provider)
    if config is None:
        return {
            "valid": False,
            "error": f"unsupported provider: {provider}",
            "balance_usd": None,
        }

    headers = {"Authorization": config["auth_template"].format(key=api_key)}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(config["url"], headers=headers)
    except httpx.TimeoutException:
        return {"valid": False, "error": "timeout", "balance_usd": None}
    except httpx.HTTPError as exc:
        return {"valid": False, "error": f"http error: {exc}", "balance_usd": None}

    if resp.status_code in (401, 403):
        return {
            "valid": False,
            "error": f"auth failed (HTTP {resp.status_code})",
            "balance_usd": None,
        }
    if resp.status_code >= 500:
        return {
            "valid": False,
            "error": f"provider error (HTTP {resp.status_code})",
            "balance_usd": None,
        }
    if not (200 <= resp.status_code < 300):
        return {
            "valid": False,
            "error": f"unexpected HTTP {resp.status_code}",
            "balance_usd": None,
        }

    balance = None
    if provider == "deepgram":
        balance = await fetch_balance(provider, api_key)

    log.info(
        "transcription_validator.validate_key.ok",
        provider=provider,
        balance_usd=balance,
    )

    return {"valid": True, "error": None, "balance_usd": balance}


async def fetch_balance(provider: str, api_key: str) -> float | None:
    """Récupère le crédit restant pour les providers qui l'exposent.

    Deepgram : GET /v1/projects → projects[].project_id, puis pour chaque
    GET /v1/projects/{project_id}/balances → list of {amount, units}.
    Sum des amounts en USD (units = 'usd').

    Autres providers : retourne None.

    Timeout 10s. Sur erreur, log warning et retourne None (pas d'exception).
    """
    if provider != "deepgram":
        return None

    headers = {"Authorization": f"Token {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            projects_resp = await client.get(
                "https://api.deepgram.com/v1/projects", headers=headers
            )
            if not (200 <= projects_resp.status_code < 300):
                return None
            projects = projects_resp.json().get("projects", [])

            total: float = 0.0
            found = False
            for proj in projects:
                project_id = proj.get("project_id")
                if not project_id:
                    continue
                bal_resp = await client.get(
                    f"https://api.deepgram.com/v1/projects/{project_id}/balances",
                    headers=headers,
                )
                if not (200 <= bal_resp.status_code < 300):
                    continue
                for balance in bal_resp.json().get("balances", []):
                    if str(balance.get("units", "")).lower() == "usd":
                        total += float(balance.get("amount", 0))
                        found = True
            return total if found else None
    except (httpx.HTTPError, ValueError) as exc:
        log.warning(
            "transcription_validator.fetch_balance_failed",
            provider=provider,
            error=str(exc),
        )
        return None
