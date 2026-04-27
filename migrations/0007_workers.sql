-- Migration 0007 : Table transcription_workers (gestion des containers workers).
-- Référence : docs/specs/01-data-model.md § Section 4.

CREATE TABLE transcription_workers (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    worker_pool_id text NOT NULL,
    container_id text,
    container_name text,
    provider text,
    status text NOT NULL,
    last_activity_at timestamptz,
    started_at timestamptz NOT NULL DEFAULT now(),
    stopped_at timestamptz,
    host text
);

CREATE INDEX transcription_workers_pool_status_idx
    ON transcription_workers (worker_pool_id, status);

CREATE INDEX transcription_workers_idle_idx
    ON transcription_workers (last_activity_at)
    WHERE status = 'idle';
