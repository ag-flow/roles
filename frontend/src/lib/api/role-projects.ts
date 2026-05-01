import { api } from './client';
import type { RoleProject } from '../types';

export async function listRoleProjects(): Promise<RoleProject[]> {
  return api<RoleProject[]>('/api/role-projects');
}

// Phase 2 sous-projet G — sections custom
export async function updateCustomSections(
  projectId: string,
  customSections: string[],
): Promise<void> {
  await api<void>(`/api/role-projects/${projectId}/custom-sections`, {
    method: 'PATCH',
    body: JSON.stringify({ custom_sections: customSections }),
  });
}
