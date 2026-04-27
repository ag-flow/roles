import { api } from './client';
import type {
  CreateSourceRequest,
  SourceResponse,
  SourceItem,
  SelectItemsRequest,
  ItemsFilter,
} from '../types';

export async function createSource(
  roleProjectId: string,
  body: CreateSourceRequest,
): Promise<SourceResponse> {
  return api(`/api/role-projects/${roleProjectId}/sources`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function discoverSource(sourceId: string): Promise<{ job_id: string }> {
  return api(`/api/sources/${sourceId}/discover`, { method: 'POST' });
}

export async function listItems(
  sourceId: string,
  filters: ItemsFilter = {},
): Promise<SourceItem[]> {
  const qs = new URLSearchParams();
  if (filters.min_duration_s !== undefined) qs.set('min_duration_s', String(filters.min_duration_s));
  if (filters.since_date) qs.set('since_date', filters.since_date);
  if (filters.status) qs.set('status', filters.status);
  if (filters.selected !== undefined) qs.set('selected', String(filters.selected));
  if (filters.limit) qs.set('limit', String(filters.limit));
  if (filters.offset) qs.set('offset', String(filters.offset));
  const path = `/api/sources/${sourceId}/items${qs.toString() ? '?' + qs.toString() : ''}`;
  return api(path);
}

export async function selectItems(
  sourceId: string,
  body: SelectItemsRequest,
): Promise<{ selected_count: number; jobs_created: number }> {
  return api(`/api/sources/${sourceId}/items/select`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}
