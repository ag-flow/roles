import { api } from './client';
import type { MistralConfig } from '../types';

export async function getMistralConfig(projectId: string): Promise<MistralConfig> {
  return api<MistralConfig>(`/api/role-projects/${projectId}/mistral-config`);
}

export async function setMistralConfig(
  projectId: string,
  secretRef: string | null,
): Promise<MistralConfig> {
  return api<MistralConfig>(`/api/role-projects/${projectId}/mistral-config`, {
    method: 'PUT',
    body: JSON.stringify({ secret_ref: secretRef }),
  });
}
