-- Migration 0005 : Tables des queues (scraping, transcription, chunking).
-- Référence : docs/specs/01-data-model.md § Section 2.

CREATE TABLE scraping_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id uuid NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    source_item_id uuid REFERENCES source_items(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    credentials_id uuid,  -- FK ajoutée en 0006
    command text NOT NULL,
    status text NOT NULL,
    priority integer DEFAULT 0,
    claimed_by text,
    claimed_at timestamptz,
    started_at timestamptz,
    completed_at timestamptz,
    attempts integer DEFAULT 0,
    max_attempts integer DEFAULT 3,
    error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX scraping_jobs_status_priority_idx
    ON scraping_jobs (status, priority DESC, created_at)
    WHERE status = 'pending';

CREATE TABLE transcription_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_item_id uuid NOT NULL REFERENCES source_items(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    audio_s3_key text NOT NULL,
    language text,
    worker_pool_id text NOT NULL,
    status text NOT NULL,
    priority integer DEFAULT 0,
    claimed_by text,
    claimed_at timestamptz,
    started_at timestamptz,
    completed_at timestamptz,
    attempts integer DEFAULT 0,
    max_attempts integer DEFAULT 3,
    provider_used text,
    cost_estimate_usd real,
    cost_actual_usd real,
    error text,
    error_history jsonb DEFAULT '[]'::jsonb,
    result_s3_key text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX transcription_jobs_pool_status_idx
    ON transcription_jobs (worker_pool_id, status, created_at);

CREATE TABLE chunking_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_item_id uuid NOT NULL REFERENCES source_items(id) ON DELETE CASCADE,
    role_project_id uuid NOT NULL REFERENCES role_projects(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    transcript_s3_key text NOT NULL,
    status text NOT NULL,
    claimed_by text,
    claimed_at timestamptz,
    started_at timestamptz,
    completed_at timestamptz,
    attempts integer DEFAULT 0,
    error text,
    chunks_produced integer,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX chunking_jobs_status_idx
    ON chunking_jobs (status, created_at)
    WHERE status = 'pending';
