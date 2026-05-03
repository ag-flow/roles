"""Endpoints REST pour la gestion des credentials (comptes réseaux sociaux).

Routes :
- GET  /api/credentials
- POST /api/credentials
- POST /api/credentials/{cred_id}/test
- DELETE /api/credentials/{cred_id}

Tous protégés par ``Depends(get_current_user)``.
Les cookies sont stockés dans Harpocrate sous le chemin :
  users/{email_slug}/scraping/{platform}/{cred_id}
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException

from role_builder.auth.dependencies import CurrentUser, get_current_user
from role_builder.db import db_pool
from role_builder.db_helpers import credentials as creds_helper
from role_builder.schemas.credentials import (
    CreateCredentialRequest,
    TestCredentialResponse,
    UserCredentialOut,
)
from role_builder.services import credentials_validator
from role_builder.services.user_vault import (
    build_credentials_vault_name,
    get_service as _get_vault_service,
)

router = APIRouter()
log = structlog.get_logger(__name__)


@router.get("/credentials", response_model=list[UserCredentialOut])
async def list_credentials_endpoint(
    platform: str | None = None,
    user: CurrentUser = Depends(get_current_user),
) -> list[UserCredentialOut]:
    """Retourne les credentials de l'utilisateur courant, filtrés par plateforme si fourni."""
    rows = await creds_helper.list_credentials(
        user_id=user.user_id,
        platform=platform,
        pool=db_pool.pool,
    )
    return [UserCredentialOut(**r) for r in rows]


@router.post("/credentials", response_model=UserCredentialOut, status_code=201)
async def create_credential_endpoint(
    request: CreateCredentialRequest,
    user: CurrentUser = Depends(get_current_user),
) -> UserCredentialOut:
    """Crée un nouveau credential après validation des cookies.

    Étapes :
    1. Validation des cookies (format + contenu)
    2. Génération d'un ID + chemin vault
    3. Stockage des cookies dans Harpocrate
    4. Insertion des métadonnées en base
    5. Retour du DTO créé
    """
    result = await credentials_validator.validate_cookies(
        request.platform,
        request.cookies_b64,
    )
    if not result["valid"]:
        raise HTTPException(
            status_code=400,
            detail=result["error"] or "invalid cookies",
        )

    cred_id = uuid4()
    secret_name = build_credentials_vault_name(user.email, request.platform, cred_id)

    await _get_vault_service().write(secret_name, request.cookies_b64)

    now = datetime.now(UTC)
    inserted_id = await creds_helper.insert_user_credential(
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        platform=request.platform,
        label=request.label,
        vault_secret_name=secret_name,
        status="active",
        last_validated_at=now,
        expires_at=result.get("expires_at"),
        pool=db_pool.pool,
    )

    log.info(
        "credentials.created",
        credential_id=str(inserted_id),
        platform=request.platform,
        user_id=str(user.user_id),
    )

    row = await creds_helper.get_credential(
        inserted_id,
        user_id=user.user_id,
        pool=db_pool.pool,
    )
    if row is None:
        raise HTTPException(status_code=500, detail="failed to retrieve created credential")
    return UserCredentialOut(**row)


@router.post("/credentials/{cred_id}/test", response_model=TestCredentialResponse)
async def test_credential_endpoint(
    cred_id: UUID,
    user: CurrentUser = Depends(get_current_user),
) -> TestCredentialResponse:
    """Revalide un credential existant en récupérant ses cookies depuis le vault."""
    cred = await creds_helper.get_credential(
        cred_id,
        user_id=user.user_id,
        pool=db_pool.pool,
    )
    if cred is None:
        raise HTTPException(status_code=404, detail="credential not found")

    cookies_b64 = await _get_vault_service().read(cred["vault_secret_name"])

    if not cookies_b64:
        await creds_helper.update_credential_status(
            cred_id,
            status="invalid",
            pool=db_pool.pool,
        )
        return TestCredentialResponse(
            status="invalid",
            last_validated_at=None,
            error="cookies missing from vault",
        )

    result = await credentials_validator.validate_cookies(cred["platform"], cookies_b64)

    new_status = "active" if result["valid"] else "invalid"
    now = datetime.now(UTC)
    await creds_helper.update_credential_status(
        cred_id,
        status=new_status,
        last_validated_at=now,
        pool=db_pool.pool,
    )

    log.info("credentials.tested", credential_id=str(cred_id), result=new_status)
    return TestCredentialResponse(
        status=new_status,
        last_validated_at=now,
        error=result.get("error"),
    )


@router.delete("/credentials/{cred_id}", status_code=204)
async def delete_credential_endpoint(
    cred_id: UUID,
    user: CurrentUser = Depends(get_current_user),
) -> None:
    """Supprime un credential : efface les cookies dans le vault puis la ligne en base."""
    cred = await creds_helper.get_credential(
        cred_id,
        user_id=user.user_id,
        pool=db_pool.pool,
    )
    if cred is None:
        raise HTTPException(status_code=404, detail="credential not found")

    await _get_vault_service().try_delete(cred["vault_secret_name"])

    await creds_helper.delete_credential(cred_id, pool=db_pool.pool)
    log.info("credentials.deleted", credential_id=str(cred_id))
