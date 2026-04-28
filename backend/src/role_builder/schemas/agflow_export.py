"""Schémas Pydantic pour les routes Sprint 7 — export ag.flow."""

from __future__ import annotations

from pydantic import BaseModel


class PushToAgflowRequest(BaseModel):
    generate_prompts: bool = False


class PushToAgflowResponse(BaseModel):
    agflow_role_id: str
    zip_size_bytes: int
    documents_count: int | None
    prompt_generated: bool
    agflow_url: str


class PreviewSectionDoc(BaseModel):
    name: str
    size: int


class PreviewSection(BaseModel):
    name: str
    documents: list[PreviewSectionDoc]


class PreviewZipResponse(BaseModel):
    display_name: str
    description: str | None
    identity_length: int
    target_role_id: str | None
    sections: list[PreviewSection]
    ready_to_push: bool
    missing: list[str]


class GeneratePromptsResponse(BaseModel):
    status: str
    target_role_id: str
