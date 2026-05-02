"""Endpoint REST pour le menu hamburger d'apps cross-modules.

Lit ``apps.json`` (path overridable via ``settings.apps_file``, sinon
``/app/apps.json`` en image docker, sinon ``../apps.json`` depuis le
runtime dev local). Si le fichier manque ou est invalide, retourne
``{"urls": []}`` — le menu se cache silencieusement côté frontend.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends
from pydantic import ValidationError

from role_builder.auth.dependencies import CurrentUser, get_current_user
from role_builder.config import settings
from role_builder.schemas.apps import AppEntry, AppsResponse

router = APIRouter()
log = structlog.get_logger(__name__)


def _resolve_apps_file() -> Path:
    if settings.apps_file is not None:
        return Path(settings.apps_file)
    docker_path = Path("/app/apps.json")
    if docker_path.is_file():
        return docker_path
    # Dev local : remonter depuis backend/src/role_builder/routes/apps.py
    return Path(__file__).resolve().parents[4] / "apps.json"


def _load_apps() -> list[AppEntry]:
    path = _resolve_apps_file()
    if not path.is_file():
        log.info("apps.json.missing", path=str(path))
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("apps.json.invalid", path=str(path), error=str(exc))
        return []
    urls = raw.get("urls", []) if isinstance(raw, dict) else []
    if not isinstance(urls, list):
        log.warning("apps.json.urls_not_list", path=str(path))
        return []
    entries: list[AppEntry] = []
    for item in urls:
        try:
            entries.append(AppEntry.model_validate(item))
        except ValidationError as exc:
            log.warning("apps.json.entry_invalid", item=item, error=str(exc))
            continue
    return entries


@router.get("/admin/apps", response_model=AppsResponse)
async def list_apps(
    user: Annotated[CurrentUser, Depends(get_current_user)],  # noqa: ARG001 — auth gate
) -> AppsResponse:
    """Retourne la liste des apps cross-modules (menu hamburger TopBar)."""
    return AppsResponse(urls=_load_apps())
