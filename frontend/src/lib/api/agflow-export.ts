import { api } from './client';
import type {
  PushPreview,
  PushToAgflowRequest,
  PushToAgflowResponse,
} from '../types';

// Empty = relative URL → passe par le proxy Next.js
// (cf. ``app/api/[...path]/route.ts``) qui injecte le Bearer token de la
// session côté serveur.
const API_BASE = '';

export async function previewZip(projectId: string): Promise<PushPreview> {
  return api<PushPreview>(`/api/role-projects/${projectId}/preview-zip`);
}

export async function pushToAgflow(
  projectId: string,
  body: PushToAgflowRequest,
): Promise<PushToAgflowResponse> {
  return api<PushToAgflowResponse>(
    `/api/role-projects/${projectId}/push-to-agflow`,
    {
      method: 'POST',
      body: JSON.stringify(body),
    },
  );
}

export async function generatePromptsOnAgflow(
  projectId: string,
): Promise<{ status: string; target_role_id: string }> {
  return api<{ status: string; target_role_id: string }>(
    `/api/role-projects/${projectId}/generate-prompts-on-agflow`,
    { method: 'POST' },
  );
}

/**
 * URL absolue du ZIP pour un téléchargement direct (`<a href={...} download>`).
 * Pas un wrapper fetch — c'est juste l'URL à donner au navigateur.
 */
export function downloadZipUrl(projectId: string): string {
  return `${API_BASE}/api/role-projects/${projectId}/download-zip`;
}
