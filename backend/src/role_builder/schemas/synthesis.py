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
