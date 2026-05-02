import { api } from './client';
import type { AppsResponse } from '../types';

export async function getApps(): Promise<AppsResponse> {
  return api<AppsResponse>('/api/admin/apps');
}
