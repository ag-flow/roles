import { api } from './client';
import type {
  RoleDocument,
  RoleDocumentsBySection,
} from '../types';

export async function listRoleDocumentsGrouped(
  projectId: string,
): Promise<RoleDocumentsBySection> {
  return api<RoleDocumentsBySection>(
    `/api/role-projects/${projectId}/role-documents`,
  );
}

export async function getRoleDocument(docId: string): Promise<RoleDocument> {
  return api<RoleDocument>(`/api/role-documents/${docId}`);
}

export async function listRoleDocumentVersions(
  docId: string,
): Promise<RoleDocument[]> {
  return api<RoleDocument[]>(`/api/role-documents/${docId}/versions`);
}

export async function updateRoleDocumentContent(
  docId: string,
  content: string,
): Promise<RoleDocument> {
  return api<RoleDocument>(`/api/role-documents/${docId}`, {
    method: 'PATCH',
    body: JSON.stringify({ content }),
  });
}

export async function lockRoleDocument(
  docId: string,
): Promise<{ status: string }> {
  return api<{ status: string }>(`/api/role-documents/${docId}/lock`, {
    method: 'POST',
  });
}

export async function unlockRoleDocument(
  docId: string,
): Promise<{ status: string }> {
  return api<{ status: string }>(`/api/role-documents/${docId}/unlock`, {
    method: 'POST',
  });
}

export async function setCurrentRoleDocument(
  docId: string,
): Promise<{ status: string }> {
  return api<{ status: string }>(`/api/role-documents/${docId}/set-current`, {
    method: 'POST',
  });
}

export async function regenerateRoleDocument(
  docId: string,
  instructionOverride?: string,
): Promise<{ run_id: string }> {
  return api<{ run_id: string }>(`/api/role-documents/${docId}/regenerate`, {
    method: 'POST',
    body: JSON.stringify({
      instruction_override: instructionOverride ?? null,
    }),
  });
}
