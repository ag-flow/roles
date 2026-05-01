"""DTOs Pydantic pour les endpoints GitHub (Sprint 8)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID  # noqa: I001 — placé après pour cohérence avec autres schemas

from pydantic import BaseModel

LicenseChoice = Literal[
    "none",
    "polyform-nc",
    "cc-by-nc-sa-4.0",
    "cc-by-4.0",
    "mit",
]


class GithubIntegrationStatus(BaseModel):
    connected: bool
    github_login: str | None = None
    scope: str | None = None
    last_validated_at: datetime | None = None


class GithubIntegrationItem(BaseModel):
    """Phase 2 D : représentation d'une intégration dans une liste."""

    id: UUID
    github_login: str
    github_user_id: int
    scope: str
    last_validated_at: datetime | None = None
    created_at: datetime


class StartOAuthResponse(BaseModel):
    redirect_url: str


class CallbackResponse(BaseModel):
    status: str
    github_login: str


class GithubRepo(BaseModel):
    full_name: str
    private: bool
    default_branch: str
    html_url: str


class PublicationConfigOut(BaseModel):
    role_project_id: UUID
    repo_full_name: str
    target_subdirectory: str
    branch: str
    commit_message_template: str
    license_choice: LicenseChoice


class PublicationConfigRequest(BaseModel):
    repo_full_name: str
    target_subdirectory: str
    branch: str = "main"
    commit_message_template: str = "Update role {role_name}"
    license_choice: LicenseChoice = "none"


class PublishResponse(BaseModel):
    commit_sha: str | None
    url: str
    files_count: int
    tag_name: str | None = None
    tag_url: str | None = None


class PublicationOut(BaseModel):
    id: UUID
    role_project_id: UUID
    user_id: UUID
    commit_sha: str
    published_at: datetime
    files_count: int | None = None
    summary: str | None = None
