import { api } from './client';
import type { Run } from '../types';

export async function listRuns(
  projectId: string,
  opts: { status?: string; limit?: number } = {},
): Promise<Run[]> {
  const params = new URLSearchParams();
  if (opts.status) params.set('status', opts.status);
  if (opts.limit !== undefined) params.set('limit', String(opts.limit));
  const qs = params.toString();
  return api<Run[]>(`/api/role-projects/${projectId}/runs${qs ? `?${qs}` : ''}`);
}

export async function getRun(runId: string): Promise<Run> {
  return api<Run>(`/api/runs/${runId}`);
}
