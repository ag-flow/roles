"""Endpoints REST pour la gestion des clés API de transcription.

Routes :
- GET    /api/transcription-keys
- POST   /api/transcription-keys
- PATCH  /api/transcription-keys/{key_id}
- POST   /api/transcription-keys/{key_id}/test
- PATCH  /api/transcription-keys/{key_id}/quota
- GET    /api/transcription-keys/{key_id}/usage
- DELETE /api/transcription-keys/{key_id}

Tous protégés par ``Depends(get_current_user)``.
La clé API réelle est stockée dans Harpocrate sous le chemin :
  users/{email_slug}/transcription/{provider}/{harpocrate_key}
La DB enregistre la référence vault : ${vault://api1:<chemin>}
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException

from role_builder.auth.dependencies import CurrentUser, get_current_user
from role_builder.db import db_pool
from role_builder.db_helpers import transcription_keys as keys_helper
from role_builder.schemas.transcription_keys import (
    CreateTranscriptionKeyRequest,
    TestKeyResponse,
    TranscriptionKeyOut,
    UpdateQuotaRequest,
    UpdateTranscriptionKeyRequest,
    UsageResponse,
)
from role_builder.services import transcription_validator
from role_builder.services.user_vault import (
    build_transcription_vault_path,
    build_vault_ref,
    extract_vault_path,
)
from role_builder.services.user_vault import (
    get_service as _get_vault_service,
)

router = APIRouter()
log = structlog.get_logger(__name__)


async def _trigger_worker_provisioning(user_id: UUID) -> None:
    """Best-effort : log l'intention de provisionner les workers.

    NOTE DETTE TECHNIQUE : WorkerManager est un singleton démarré dans le
    lifespan FastAPI (app.state non exposé via Depends). Le triggering réel
    nécessite un refactor pour exposer get_worker_manager comme Depends.
    À reporter en Phase 2.
    """
    try:
        log.info(
            "transcription_keys.worker_provisioning_skipped",
            user_id=str(user_id),
            reason="worker_manager_not_exposed_via_depends",
        )
    except Exception:
        log.exception("transcription_keys.worker_provisioning_failed", user_id=str(user_id))


async def _trigger_worker_stop(key_id: UUID) -> None:
    """Best-effort : log l'intention d'arrêter les workers d'une clé.

    Même dette que _trigger_worker_provisioning.
    """
    try:
        log.info(
            "transcription_keys.worker_stop_skipped",
            key_id=str(key_id),
            reason="worker_manager_not_exposed_via_depends",
        )
    except Exception:
        log.exception("transcription_keys.worker_stop_failed", key_id=str(key_id))


@router.get("/transcription-keys", response_model=list[TranscriptionKeyOut])
async def list_keys_endpoint(
    user: CurrentUser = Depends(get_current_user),
) -> list[TranscriptionKeyOut]:
    """Liste toutes les clés de l'utilisateur courant."""
    rows = await keys_helper.list_keys_for_user(user.user_id, pool=db_pool.pool)
    return [TranscriptionKeyOut(**r) for r in rows]


@router.post("/transcription-keys", response_model=TranscriptionKeyOut, status_code=201)
async def create_key_endpoint(
    request: CreateTranscriptionKeyRequest,
    user: CurrentUser = Depends(get_current_user),
) -> TranscriptionKeyOut:
    """Crée une clé transcription après validation auprès du provider.

    Étapes :
    1. Validation via l'API du provider
    2. Génération key_id + nom de secret vault
    3. Stockage de la clé dans vault
    4. Insertion des métadonnées en base
    5. Mise à jour du solde si retourné
    6. Best-effort worker provisioning
    7. Retour du DTO créé
    """
    result = await transcription_validator.validate_transcription_key(
        request.provider, request.api_key
    )
    if not result["valid"]:
        raise HTTPException(
            status_code=400,
            detail=result.get("error") or "invalid api key",
        )

    path = build_transcription_vault_path(user.email, request.provider, request.harpocrate_key)
    vault_ref = build_vault_ref(path)

    await _get_vault_service().write(path, request.api_key)

    inserted_id = await keys_helper.insert_transcription_key(
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        provider=request.provider,
        label=request.label,
        vault_secret_name=vault_ref,
        workers_count=request.workers_count,
        is_primary=request.is_primary,
        is_fallback=request.is_fallback,
        pool=db_pool.pool,
    )

    if result.get("balance_usd") is not None:
        await keys_helper.update_key_balance(
            inserted_id,
            balance_usd=result["balance_usd"],
            checked_at=datetime.now(UTC),
            pool=db_pool.pool,
        )

    await _trigger_worker_provisioning(user.user_id)

    log.info(
        "transcription_keys.created",
        key_id=str(inserted_id),
        provider=request.provider,
        user_id=str(user.user_id),
    )

    row = await keys_helper.get_key(inserted_id, user_id=user.user_id, pool=db_pool.pool)
    if row is None:
        raise HTTPException(status_code=500, detail="failed to retrieve created key")
    return TranscriptionKeyOut(**row)


@router.patch("/transcription-keys/{key_id}", response_model=TranscriptionKeyOut)
async def update_key_endpoint(
    key_id: UUID,
    request: UpdateTranscriptionKeyRequest,
    user: CurrentUser = Depends(get_current_user),
) -> TranscriptionKeyOut:
    """Met à jour les settings d'une clé (workers_count, is_primary, is_fallback)."""
    existing = await keys_helper.get_key(key_id, user_id=user.user_id, pool=db_pool.pool)
    if existing is None:
        raise HTTPException(status_code=404, detail="key not found")

    update_kwargs = request.model_dump(exclude_none=True)
    if update_kwargs:
        await keys_helper.update_key_settings(key_id, pool=db_pool.pool, **update_kwargs)
        if "is_primary" in update_kwargs or "workers_count" in update_kwargs:
            await _trigger_worker_provisioning(user.user_id)

    row = await keys_helper.get_key(key_id, user_id=user.user_id, pool=db_pool.pool)
    if row is None:
        raise HTTPException(status_code=500, detail="key vanished after update")
    return TranscriptionKeyOut(**row)


@router.post("/transcription-keys/{key_id}/test", response_model=TestKeyResponse)
async def test_key_endpoint(
    key_id: UUID,
    user: CurrentUser = Depends(get_current_user),
) -> TestKeyResponse:
    """Revalide une clé en l'envoyant au provider et met à jour le statut en base."""
    key = await keys_helper.get_key(key_id, user_id=user.user_id, pool=db_pool.pool)
    if key is None:
        raise HTTPException(status_code=404, detail="key not found")

    path = extract_vault_path(key["vault_secret_name"])
    raw_key = await _get_vault_service().read(path)

    if raw_key is None:
        await keys_helper.mark_invalid(key_id, pool=db_pool.pool)
        return TestKeyResponse(
            status="invalid",
            last_validated_at=None,
            balance_usd=None,
            error="api_key missing from vault",
        )

    api_key = raw_key
    result = await transcription_validator.validate_transcription_key(key["provider"], api_key)
    new_status = "active" if result["valid"] else "invalid"
    now = datetime.now(UTC)

    if not result["valid"]:
        await keys_helper.mark_invalid(key_id, pool=db_pool.pool)
    else:
        async with db_pool.pool.acquire() as conn:
            await conn.execute(
                "UPDATE user_transcription_keys "
                "SET status = 'active', last_validated_at = $2, updated_at = now() "
                "WHERE id = $1",
                key_id,
                now,
            )

    if result.get("balance_usd") is not None:
        await keys_helper.update_key_balance(
            key_id,
            balance_usd=result["balance_usd"],
            checked_at=now,
            pool=db_pool.pool,
        )

    log.info("transcription_keys.tested", key_id=str(key_id), result=new_status)
    return TestKeyResponse(
        status=new_status,
        last_validated_at=now,
        balance_usd=result.get("balance_usd"),
        error=result.get("error"),
    )


@router.patch("/transcription-keys/{key_id}/quota", response_model=TranscriptionKeyOut)
async def update_quota_endpoint(
    key_id: UUID,
    request: UpdateQuotaRequest,
    user: CurrentUser = Depends(get_current_user),
) -> TranscriptionKeyOut:
    """Met à jour le plafond mensuel d'une clé."""
    existing = await keys_helper.get_key(key_id, user_id=user.user_id, pool=db_pool.pool)
    if existing is None:
        raise HTTPException(status_code=404, detail="key not found")

    if request.monthly_cap_usd is not None:
        await keys_helper.update_key_settings(
            key_id,
            monthly_cap_usd=request.monthly_cap_usd,
            pool=db_pool.pool,
        )

    row = await keys_helper.get_key(key_id, user_id=user.user_id, pool=db_pool.pool)
    if row is None:
        raise HTTPException(status_code=500, detail="key vanished after quota update")
    return TranscriptionKeyOut(**row)


@router.get("/transcription-keys/{key_id}/usage", response_model=UsageResponse)
async def get_usage_endpoint(
    key_id: UUID,
    user: CurrentUser = Depends(get_current_user),
) -> UsageResponse:
    """Retourne les métriques d'usage (spend, cap, % utilisé, solde) d'une clé."""
    key = await keys_helper.get_key(key_id, user_id=user.user_id, pool=db_pool.pool)
    if key is None:
        raise HTTPException(status_code=404, detail="key not found")

    cap = key["monthly_cap_usd"]
    spend = key["current_month_spend_usd"]
    pct = (spend / cap * 100) if (cap is not None and cap > 0) else None
    return UsageResponse(
        current_month_spend_usd=spend,
        monthly_cap_usd=cap,
        pct_used=pct,
        last_balance_check_at=key["last_balance_check_at"],
        current_balance_usd=key["current_balance_usd"],
    )


@router.delete("/transcription-keys/{key_id}", status_code=204)
async def delete_key_endpoint(
    key_id: UUID,
    user: CurrentUser = Depends(get_current_user),
) -> None:
    """Supprime une clé : arrêt workers (best-effort), purge vault, suppression BDD."""
    key = await keys_helper.get_key(key_id, user_id=user.user_id, pool=db_pool.pool)
    if key is None:
        raise HTTPException(status_code=404, detail="key not found")

    await _trigger_worker_stop(key_id)

    path = extract_vault_path(key["vault_secret_name"])
    await _get_vault_service().try_delete(path)

    await keys_helper.delete_key(key_id, pool=db_pool.pool)
    log.info("transcription_keys.deleted", key_id=str(key_id))
