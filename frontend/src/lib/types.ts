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
  | 'workers_changes'
  | 'keys_changes';

// ─── Apps menu (cross-modules launcher) ──────────────────────────────────────

export interface AppEntry {
  key: string;
  label: string;
  icon: string;
  url: string;
}

export interface AppsResponse {
  urls: AppEntry[];
}

// ─── My Stack types ───────────────────────────────────────────────────────────

export type CredentialPlatform = 'youtube' | 'instagram' | 'tiktok';
export type CredentialStatus = 'active' | 'expired' | 'invalid' | 'revoked';

export interface UserCredential {
  id: string;
  platform: CredentialPlatform;
  label: string | null;
  status: CredentialStatus;
  last_validated_at: string | null;
  expires_at: string | null;
  created_at: string;
}

export interface TestCredentialResult {
  status: string;
  last_validated_at: string | null;
  error: string | null;
}

export type TranscriptionProvider =
  | 'openai-whisper'
  | 'deepgram'
  | 'assemblyai'
  | 'speechmatics';

export type TranscriptionKeyStatus = 'active' | 'low' | 'exhausted' | 'invalid';

export interface TranscriptionKey {
  id: string;
  provider: TranscriptionProvider;
  label: string | null;
  status: TranscriptionKeyStatus;
  is_primary: boolean;
  is_fallback: boolean;
  workers_count: number;
  monthly_cap_usd: number | null;
  current_month_spend_usd: number;
  current_balance_usd: number | null;
  last_balance_check_at: string | null;
  last_validated_at: string | null;
  created_at: string;
}

export interface TestKeyResult {
  status: string;
  last_validated_at: string | null;
  balance_usd: number | null;
  error: string | null;
}

export interface KeyUsage {
  current_month_spend_usd: number;
  monthly_cap_usd: number | null;
  pct_used: number | null;
  last_balance_check_at: string | null;
  current_balance_usd: number | null;
}

export interface RoleProject {
  id: string;
  tenant_id: string;
  user_id: string;
  display_name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}
