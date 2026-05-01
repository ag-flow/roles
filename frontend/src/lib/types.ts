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
  | 'keys_changes'
  | 'agflow_push_events';

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
  is_obsolete?: boolean;
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

// ─── Sprint 7 Phase D : Role documents (UI editor) ───────────────────────────

export interface RoleDocumentSummary {
  id: string;
  section: string;
  name: string;
  version: number;
  is_current: boolean;
  locked: boolean;
  updated_at: string;
}

export interface RoleDocumentsBySection {
  sections: Record<string, RoleDocumentSummary[]>;
}

// ─── Sprint 7 Phase D : Push to ag.flow ──────────────────────────────────────

export interface PreviewSectionDoc {
  name: string;
  size: number;
}

export interface PreviewSection {
  name: string;
  documents: PreviewSectionDoc[];
}

export interface PushPreview {
  display_name: string;
  description: string | null;
  identity_length: number;
  target_role_id: string | null;
  sections: PreviewSection[];
  ready_to_push: boolean;
  missing: string[];
}

export interface PushToAgflowRequest {
  generate_prompts: boolean;
}

export interface PushToAgflowResponse {
  agflow_role_id: string;
  zip_size_bytes: number;
  documents_count: number | null;
  prompt_generated: boolean;
  agflow_url: string;
}

export type PushStep =
  | 'zip_built'
  | 'role_ready'
  | 'zip_uploaded'
  | 'prompts_generated'
  | 'done'
  | 'failed';

export type PushStatus = 'in_progress' | 'done' | 'failed';

export interface PushEventPayload {
  tenant_id: string;
  project_id: string;
  step: PushStep;
  status: PushStatus;
  detail?: Record<string, unknown>;
}

// ─── Sprint 8 : GitHub publication ───────────────────────────────────────────

export type LicenseChoice =
  | 'none'
  | 'polyform-nc'
  | 'cc-by-nc-sa-4.0'
  | 'cc-by-4.0'
  | 'mit';

export interface GithubIntegrationStatus {
  connected: boolean;
  github_login: string | null;
  scope: string | null;
  last_validated_at: string | null;
}

export interface GithubRepo {
  full_name: string;
  private: boolean;
  default_branch: string;
  html_url: string;
}

export interface PublicationConfig {
  role_project_id: string;
  repo_full_name: string;
  target_subdirectory: string;
  branch: string;
  commit_message_template: string;
  license_choice: LicenseChoice;
}

export interface PublicationConfigRequest {
  repo_full_name: string;
  target_subdirectory: string;
  branch?: string;
  commit_message_template?: string;
  license_choice?: LicenseChoice;
}

export interface PublishResponse {
  commit_sha: string | null;
  url: string;
  files_count: number;
  /** Nom du tag annoté créé (ex: 'role-ux-clea-v3') ou null. */
  tag_name?: string | null;
  /** URL GitHub releases du tag, ou null. */
  tag_url?: string | null;
}

export interface Publication {
  id: string;
  role_project_id: string;
  user_id: string;
  commit_sha: string;
  published_at: string;
  files_count: number | null;
  summary: string | null;
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

export interface MistralConfig {
  secret_ref: string | null;
  status: 'configured' | 'not-configured';
}

export interface RoleProject {
  id: string;
  tenant_id: string;
  user_id: string;
  display_name: string;
  description: string | null;
  global_directives: string | null;
  mistral_secret_ref: string | null;
  identity: string | null;
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
