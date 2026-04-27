import { api } from './client';
import type { Prompt, PromptVersion } from '../types';

export async function listPrompts(): Promise<Prompt[]> {
  return api<Prompt[]>('/api/prompts');
}

export async function listVersions(promptId: string): Promise<PromptVersion[]> {
  return api<PromptVersion[]>(`/api/prompts/${promptId}/versions`);
}

export async function createVersion(promptId: string, template: string): Promise<PromptVersion> {
  return api<PromptVersion>(`/api/prompts/${promptId}/versions`, {
    method: 'POST',
    body: JSON.stringify({ template }),
  });
}

export async function setSystemDefault(promptId: string, versionId: string): Promise<void> {
  await api<void>(`/api/prompts/${promptId}/system-default/${versionId}`, { method: 'PUT' });
}
