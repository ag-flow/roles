import { api } from './client';

interface TriggerOpts {
  prompt_version_id?: string;
  instruction_override?: string;
}

export async function triggerExtraction(
  projectId: string,
  body: TriggerOpts & { chunks_per_batch?: number } = {},
): Promise<{ run_id: string }> {
  return api<{ run_id: string }>(`/api/role-projects/${projectId}/runs/extract`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function triggerClustering(
  projectId: string,
  body: TriggerOpts & { signal_run_id?: string } = {},
): Promise<{ run_id: string }> {
  return api<{ run_id: string }>(`/api/role-projects/${projectId}/runs/cluster`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function triggerDecomposition(
  projectId: string,
  body: TriggerOpts & { cluster_run_id?: string } = {},
): Promise<{ run_id: string }> {
  return api<{ run_id: string }>(`/api/role-projects/${projectId}/runs/decompose`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function triggerDocumentWriting(
  projectId: string,
  planId: string,
  parallelism = 3,
): Promise<{ run_ids: string[] }> {
  return api<{ run_ids: string[] }>(`/api/role-projects/${projectId}/runs/write-documents`, {
    method: 'POST',
    body: JSON.stringify({ plan_id: planId, parallelism }),
  });
}

export async function triggerIdentitySynthesis(
  projectId: string,
  body: TriggerOpts = {},
): Promise<{ run_id: string }> {
  return api<{ run_id: string }>(`/api/role-projects/${projectId}/runs/synthesize-identity`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function regenerateDocument(
  docId: string,
  instructionOverride?: string,
): Promise<{ run_id: string }> {
  return api<{ run_id: string }>(`/api/role-documents/${docId}/regenerate`, {
    method: 'POST',
    body: JSON.stringify({ instruction_override: instructionOverride ?? null }),
  });
}

export async function setCurrentVersion(docId: string): Promise<{ status: string }> {
  return api<{ status: string }>(`/api/role-documents/${docId}/set-current`, { method: 'POST' });
}
