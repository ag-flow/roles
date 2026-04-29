"""DTOs pour les endpoints de déclenchement de la synthèse."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class TriggerExtractRequest(BaseModel):
    prompt_version_id: UUID | None = None
    instruction_override: str | None = None
    chunks_per_batch: int = 5


class TriggerClusterRequest(BaseModel):
    signal_run_id: UUID | None = None
    prompt_version_id: UUID | None = None
    instruction_override: str | None = None


class TriggerDecomposeRequest(BaseModel):
    cluster_run_id: UUID | None = None
    prompt_version_id: UUID | None = None
    instruction_override: str | None = None


class TriggerWriteDocumentsRequest(BaseModel):
    plan_id: UUID
    parallelism: int = 3


class TriggerIdentityRequest(BaseModel):
    prompt_version_id: UUID | None = None
    instruction_override: str | None = None


class RegenerateDocumentRequest(BaseModel):
    instruction_override: str | None = None


class TriggerOutSingleRun(BaseModel):
    run_id: UUID


class TriggerOutMultipleRuns(BaseModel):
    run_ids: list[UUID]


class TriggerFullPipelineRequest(BaseModel):
    """Body de POST /role-projects/{id}/runs/full-pipeline.

    Tous les champs sont optionnels — chaque étage utilise son prompt par
    défaut si non fourni. ``include_identity`` permet de skip le 5e étage
    si l'identity est déjà OK et qu'on régénère juste les sections.
    """

    chunks_per_batch: int = 5
    parallelism: int = 3
    include_identity: bool = True
    extract_instruction_override: str | None = None
    cluster_instruction_override: str | None = None
    decompose_instruction_override: str | None = None
    identity_instruction_override: str | None = None


class FullPipelineResponse(BaseModel):
    """Tous les run_ids créés par le pipeline complet."""

    extract_run_id: UUID
    cluster_run_id: UUID
    decompose_run_id: UUID
    document_run_ids: list[UUID]
    identity_run_id: UUID | None = None
