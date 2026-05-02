"""DTO Pydantic pour le menu hamburger d'apps cross-modules.

Phase 2 : permet d'afficher un app launcher dans la TopBar listant les autres
modules de la suite agflow (Docker, Security, Workflow, etc.). La source de
vérité est ``apps.json`` à la racine du repo, monté en bind mount sur le
backend (cf. docker-compose.yml).
"""

from __future__ import annotations

from pydantic import BaseModel, HttpUrl


class AppEntry(BaseModel):
    key: str
    label: str
    icon: HttpUrl
    url: HttpUrl


class AppsResponse(BaseModel):
    urls: list[AppEntry]
