"""Endpoint /api/version — info de version exposée publiquement.

Utile pour :
- Footer du frontend (montre quelle version est déployée)
- Sanity check au déploiement (CI peut comparer la version attendue à
  celle exposée par le backend après déploiement)
- Support utilisateur (la version remontée avec les bugs reports)

Pas d'auth : c'est de l'info publique au même titre que le titre de l'app.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from role_builder import __version__

router = APIRouter()


class VersionResponse(BaseModel):
    version: str
    name: str


@router.get("/version", response_model=VersionResponse)
async def version_info() -> VersionResponse:
    """Retourne la version courante du backend.

    Pas d'auth : info publique. Frontend / CI / curl sans token peuvent y
    accéder.
    """
    return VersionResponse(version=__version__, name="Role Builder")
