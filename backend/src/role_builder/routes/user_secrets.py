"""Endpoints REST pour les secrets utilisateur typés.

Routes :
- GET    /api/secrets
- POST   /api/secrets
- DELETE /api/secrets/{secret_id}

Tous protégés par ``Depends(get_current_user)``. La valeur d'un secret ne
ressort jamais de l'API : elle part en base chiffrée (storage=local) ou
dans le wallet Harpocrate choisi (storage=wallet).
"""

from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException

from role_builder.auth.dependencies import CurrentUser, get_current_user
from role_builder.db import db_pool
from role_builder.db_helpers import user_secrets as secrets_helper
from role_builder.schemas.user_secrets import CreateSecretRequest, SecretOut
from role_builder.services.secret_store import (
    UnknownWalletError,
)
from role_builder.services.secret_store import (
    get_secret_store as _get_secret_store,
)

router = APIRouter()
log = structlog.get_logger(__name__)


@router.get("/secrets", response_model=list[SecretOut])
async def list_secrets_endpoint(
    secret_type: str | None = None,
    user: CurrentUser = Depends(get_current_user),
) -> list[SecretOut]:
    """Secrets de l'utilisateur courant (métadonnées seules), filtrés par type si fourni."""
    rows = await secrets_helper.list_secrets(
        user_id=user.user_id, secret_type=secret_type, pool=db_pool.pool
    )
    return [SecretOut(**r) for r in rows]


@router.post("/secrets", response_model=SecretOut, status_code=201)
async def create_secret_endpoint(
    request: CreateSecretRequest,
    user: CurrentUser = Depends(get_current_user),
) -> SecretOut:
    """Stocke un secret : local (wallet_id absent) ou wallet Harpocrate."""
    try:
        secret_id = await _get_secret_store().create_secret(
            tenant_id=user.tenant_id,
            user_id=user.user_id,
            secret_type=request.secret_type,
            label=request.label,
            value=request.value,
            wallet_id=request.wallet_id,
            pool=db_pool.pool,
        )
    except UnknownWalletError as exc:
        raise HTTPException(status_code=404, detail="wallet not found") from exc

    log.info(
        "secrets.created",
        secret_id=str(secret_id),
        secret_type=request.secret_type,
        storage="wallet" if request.wallet_id else "local",
        user_id=str(user.user_id),
    )

    row = await secrets_helper.get_secret(
        secret_id=secret_id, user_id=user.user_id, pool=db_pool.pool
    )
    if row is None:
        raise HTTPException(status_code=500, detail="failed to retrieve created secret")
    return SecretOut(**row)


@router.delete("/secrets/{secret_id}", status_code=204)
async def delete_secret_endpoint(
    secret_id: UUID,
    user: CurrentUser = Depends(get_current_user),
) -> None:
    """Supprime un secret non référencé par un service ; 409 sinon."""
    secret = await secrets_helper.get_secret(
        secret_id=secret_id, user_id=user.user_id, pool=db_pool.pool
    )
    if secret is None:
        raise HTTPException(status_code=404, detail="secret not found")

    refs = await secrets_helper.count_service_references(
        secret_id=secret_id, pool=db_pool.pool
    )
    if refs > 0:
        raise HTTPException(
            status_code=409,
            detail=f"secret référencé par {refs} service(s) — les détacher d'abord",
        )

    await _get_secret_store().delete_secret(secret, pool=db_pool.pool)
    log.info("secrets.deleted", secret_id=str(secret_id))
