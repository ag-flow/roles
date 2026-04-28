"""Schémas Pydantic pour la configuration Mistral d'un role_project."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class MistralConfigOut(BaseModel):
    secret_ref: str | None
    status: Literal["configured", "not-configured"]


class SetMistralConfigRequest(BaseModel):
    secret_ref: str | None = None
