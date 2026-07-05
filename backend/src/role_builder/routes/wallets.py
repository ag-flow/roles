"""Endpoints REST pour les wallets Harpocrate personnels.

Routes :
- GET    /api/wallets
- POST   /api/wallets
- DELETE /api/wallets/{wallet_id}

Tous protégés par ``Depends(get_current_user)``. Les wallets sont privés
par utilisateur ; le token est validé en direct à l'enregistrement puis
stocké chiffré (SECRET_ENCRYPTION_KEY) — jamais renvoyé par l'API.
"""

from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException

from role_builder.auth.dependencies import CurrentUser, get_current_user
from role_builder.db import db_pool
from role_builder.db_helpers import user_wallets as wallets_helper
from role_builder.schemas.wallets import CreateWalletRequest, WalletOut
from role_builder.services.secret_store import (
    InvalidWalletTokenError,
)
from role_builder.services.secret_store import (
    get_secret_store as _get_secret_store,
)

router = APIRouter()
log = structlog.get_logger(__name__)


@router.get("/wallets", response_model=list[WalletOut])
async def list_wallets_endpoint(
    user: CurrentUser = Depends(get_current_user),
) -> list[WalletOut]:
    """Wallets de l'utilisateur courant, du plus ancien au plus récent."""
    rows = await wallets_helper.list_wallets(user_id=user.user_id, pool=db_pool.pool)
    return [WalletOut(**r) for r in rows]


@router.post("/wallets", response_model=WalletOut, status_code=201)
async def create_wallet_endpoint(
    request: CreateWalletRequest,
    user: CurrentUser = Depends(get_current_user),
) -> WalletOut:
    """Enregistre un wallet après validation live du token auprès d'Harpocrate."""
    try:
        wallet_id = await _get_secret_store().register_wallet(
            tenant_id=user.tenant_id,
            user_id=user.user_id,
            label=request.label,
            token=request.api_token,
            api_url=request.api_url,
            pool=db_pool.pool,
        )
    except InvalidWalletTokenError as exc:
        raise HTTPException(status_code=400, detail=f"token refusé : {exc}") from exc

    log.info("wallets.created", wallet_id=str(wallet_id), user_id=str(user.user_id))

    row = await wallets_helper.get_wallet(
        wallet_id=wallet_id, user_id=user.user_id, pool=db_pool.pool
    )
    if row is None:
        raise HTTPException(status_code=500, detail="failed to retrieve created wallet")
    return WalletOut(**row)


@router.delete("/wallets/{wallet_id}", status_code=204)
async def delete_wallet_endpoint(
    wallet_id: UUID,
    user: CurrentUser = Depends(get_current_user),
) -> None:
    """Supprime un wallet sans secret rattaché ; 409 sinon."""
    wallet = await wallets_helper.get_wallet(
        wallet_id=wallet_id, user_id=user.user_id, pool=db_pool.pool
    )
    if wallet is None:
        raise HTTPException(status_code=404, detail="wallet not found")

    count = await wallets_helper.count_secrets_for_wallet(
        wallet_id=wallet_id, pool=db_pool.pool
    )
    if count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"wallet référencé par {count} secret(s) — les supprimer d'abord",
        )

    await wallets_helper.delete_wallet(
        wallet_id=wallet_id, user_id=user.user_id, pool=db_pool.pool
    )
    _get_secret_store().invalidate_wallet(wallet_id)
    log.info("wallets.deleted", wallet_id=str(wallet_id))
