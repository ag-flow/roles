"""Schémas Pydantic pour les role_projects."""

from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


class RoleProjectOut(BaseModel):
    """DTO de sortie pour un role_project."""

    model_config = ConfigDict(extra="allow")

    id: UUID
    tenant_id: UUID
    user_id: UUID
    display_name: str
    description: str | None = None
    global_directives: str | None = None
    mistral_secret_ref: str | None = None
    identity: str | None = None
    custom_sections: list[str] = []
    created_at: datetime
    updated_at: datetime


# Phase 2 sous-projet G — Sections custom
_SECTION_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{1,31}$")
_RESERVED_SECTIONS = {"Role", "Missions", "Skills"}
MAX_CUSTOM_SECTIONS = 5


class CustomSectionsPatch(BaseModel):
    """Body pour PATCH /role-projects/{id}/custom-sections.

    Validation : 0..5 noms, regex stricte, pas de conflit avec les sections
    standards, pas de doublons.
    """

    custom_sections: list[str]

    @field_validator("custom_sections")
    @classmethod
    def _validate(cls, v: list[str]) -> list[str]:
        if len(v) > MAX_CUSTOM_SECTIONS:
            raise ValueError(
                f"max {MAX_CUSTOM_SECTIONS} sections custom (reçu {len(v)})",
            )
        seen: set[str] = set()
        for name in v:
            if not isinstance(name, str):
                raise TypeError("custom_sections must be strings")
            if not _SECTION_NAME_RE.match(name):
                raise ValueError(
                    f"section name '{name}' invalide (regex "
                    f"^[A-Za-z][A-Za-z0-9_-]{{1,31}}$)",
                )
            if name in _RESERVED_SECTIONS:
                raise ValueError(
                    f"'{name}' est une section standard, pas custom",
                )
            if name in seen:
                raise ValueError(f"section '{name}' dupliquée")
            seen.add(name)
        return v
