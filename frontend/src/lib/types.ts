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

export interface Chunk {
  chunk_id: string;
  source_item_id: string;
  source_title: string | null;
  text: string;
  start_s: number | null;
  end_s: number | null;
}

export interface SearchResult extends Chunk {
  similarity: number;
}

export interface SearchResponse {
  query: string;
  results: SearchResult[];
}

export interface AudioUrlResponse {
  item_id: string;
  url: string;
  expires_in_s: number;
}

export interface TranscriptSegment {
  start: number;
  end: number;
  text: string;
  id?: number;
}

export interface TranscriptResponse {
  item_id: string;
  s3_key: string;
  pivot: { segments: TranscriptSegment[]; [k: string]: unknown };
}

// ─── Synthesis types ──────────────────────────────────────────────────────────

export type RunStatus = 'pending' | 'running' | 'done' | 'failed';

export interface Run {
  id: string;
  role_project_id: string;
  prompt_version_id: string;
  status: RunStatus;
  output: string | null;
  llm_provider: string | null;
  llm_model: string | null;
  tokens_input: number | null;
  tokens_output: number | null;
  cost_usd: number | null;
  instruction_override: string | null;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
  created_at: string;
}

export interface Signal {
  id: string;
  run_id: string;
  role_project_id: string;
  source_item_id: string | null;
  source_chunks: string[];
  type: string;
  content: Record<string, unknown>;
  created_at: string;
}

export interface Cluster {
  id: string;
  run_id: string;
  role_project_id: string;
  name: string;
  description: string | null;
  signal_ids: string[];
  created_at: string;
}

export interface DocumentPlan {
  id: string;
  run_id: string;
  role_project_id: string;
  section: 'Role' | 'Missions' | 'Skills';
  planned_documents: Array<{
    name: string;
    brief: string;
    supporting_signals: string[];
  }>;
  created_at: string;
}

export interface RoleDocument {
  id: string;
  role_project_id: string;
  section: string;
  name: string;
  content: string;
  source_run_id: string | null;
  version: number;
  is_current: boolean;
  locked: boolean;
  created_at: string;
  updated_at: string;
}

// ─── Prompts types ────────────────────────────────────────────────────────────

export interface Prompt {
  id: string;
  name: string;
  type: string;
  target_section: string | null;
  description: string | null;
}

export interface PromptVersion {
  id: string;
  prompt_id: string;
  version_number: number;
  template: string;
  is_system_default: boolean;
  created_at: string;
}
