"""Routes Sprint 8 — flow OAuth GitHub.

Endpoints :
- GET    /api/auth/github/start    — démarre OAuth, retourne URL GitHub
- GET    /api/auth/github/callback — callback GitHub, échange code → token
- GET    /api/auth/github/status   — statut connexion (UI Ma stack)
- DELETE /api/auth/github          — déconnexion (revoke + delete row DB)
"""

from __future__ import annotations

import secrets as py_secrets
from typing import Annotated

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException

from role_builder.auth.dependencies import CurrentUser, get_current_user
from role_builder.config import settings
from role_builder.db import db_pool
from role_builder.db_helpers import github_integrations, oauth_states
from role_builder.schemas.github import (
    CallbackResponse,
    GithubIntegrationStatus,
    StartOAuthResponse,
)
from role_builder.services.github_publish import oauth as gh_oauth_module
from role_builder.services.openbao_client import OpenBaoClient

router = APIRouter()
log = structlog.get_logger(__name__)


@router.get("/auth/github/start", response_model=StartOAuthResponse)
async def start_oauth(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> StartOAuthResponse:
    state = py_secrets.token_urlsafe(32)
    await oauth_states.insert_state(
        state=state,
        user_id=user.user_id,
        tenant_id=user.tenant_id,
        ttl_seconds=600,
        pool=db_pool.pool,
    )
    url = gh_oauth_module.gh_oauth.build_authorize_url(state)
    log.info("github.oauth.started", user_id=str(user.user_id))
    return StartOAuthResponse(redirect_url=url)


@router.get("/auth/github/callback", response_model=CallbackResponse)
async def oauth_callback(code: str, state: str) -> CallbackResponse:
    info = await oauth_states.consume_state(state, pool=db_pool.pool)
    if info is None:
        raise HTTPException(status_code=400, detail="invalid or expired state")

    user_id = info["user_id"]
    tenant_id = info["tenant_id"]

    try:
        access_token = await gh_oauth_module.gh_oauth.exchange_code(code)
        gh_user = await gh_oauth_module.gh_oauth.get_user_info(access_token)
    except httpx.HTTPStatusError as exc:
        log.exception("github.oauth.upstream_error")
        raise HTTPException(status_code=502, detail=f"GitHub: {exc}") from exc

    openbao_path = f"github-tokens/{tenant_id}/{user_id}"
    openbao = OpenBaoClient()
    try:
        await openbao.put(openbao_path, {"access_token": access_token})
    finally:
        await openbao.aclose()

    await github_integrations.upsert(
        user_id=user_id,
        tenant_id=tenant_id,
        github_login=str(gh_user["login"]),
        github_user_id=int(gh_user["id"]),
        openbao_path=openbao_path,
        scope=settings.github_oauth_scope,
        pool=db_pool.pool,
    )
    log.info(
        "github.oauth.connected",
        user_id=str(user_id),
        github_login=gh_user["login"],
    )
    return CallbackResponse(status="connected", github_login=str(gh_user["login"]))


@router.get("/auth/github/status", response_model=GithubIntegrationStatus)
async def status_endpoint(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> GithubIntegrationStatus:
    integration = await github_integrations.get_by_user_id(
        user.user_id, pool=db_pool.pool,
    )
    if integration is None:
        return GithubIntegrationStatus(connected=False)
    return GithubIntegrationStatus(
        connected=True,
        github_login=str(integration["github_login"]),
        scope=str(integration["scope"]),
        last_validated_at=integration.get("last_validated_at"),
    )


@router.delete("/auth/github")
async def disconnect(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, str]:
    integration = await github_integrations.get_by_user_id(
        user.user_id, pool=db_pool.pool,
    )
    if integration is None:
        return {"status": "not-connected"}

    openbao = OpenBaoClient()
    try:
        await openbao.delete(str(integration["openbao_path"]))
    finally:
        await openbao.aclose()

    await github_integrations.delete_by_user_id(user.user_id, pool=db_pool.pool)
    log.info("github.oauth.disconnected", user_id=str(user.user_id))
    return {"status": "disconnected"}
