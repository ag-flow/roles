export type Platform = 'youtube' | 'instagram' | 'tiktok';
export type SourceType = 'single' | 'channel' | 'playlist' | 'account';

export interface CreateSourceRequest {
  url: string;
  platform: Platform;
  source_type: SourceType;
  credentials_id?: string | null;
}

export interface SourceResponse {
  id: string;
  role_project_id: string;
  platform: string;
  source_type: string;
  url: string;
  status: string;
  discovered_count?: number | null;
  error?: string | null;
  created_at: string;
  updated_at: string;
}

export interface SourceItem {
  id: string;
  platform_item_id: string;
  title: string | null;
  duration_s: number | null;
  published_at: string | null;
  thumbnail_url: string | null;
  status: string;
  selected: boolean;
  audio_s3_key: string | null;
  error: string | null;
}

export interface SelectItemsRequest {
  item_ids: string[];
  deselect_others: boolean;
}

export interface ItemsFilter {
  min_duration_s?: number;
  since_date?: string;
  status?: string;
  selected?: boolean;
  limit?: number;
  offset?: number;
}

export interface ScrapingJob {
  id: string;
  source_id: string;
  command: string;
  status: string;
  attempts: number;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface WSEventPayload {
  table: string;
  op: string;
  tenant_id: string;
  id: string;
  status: string;
}

export type WSChannel =
  | 'source_items_changes'
  | 'runs_changes'
  | 'workers_changes'
  | 'keys_changes';
