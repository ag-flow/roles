import { api } from './client';
import type { RoleProject } from '../types';

export async function listRoleProjects(): Promise<RoleProject[]> {
  return api<RoleProject[]>('/api/role-projects');
}
