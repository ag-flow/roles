-- Migration 0006 : Tables des credentials et clés API.
-- Référence : docs/specs/01-data-model.md § Section 3.

CREATE TABLE user_credentials (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    user_id uuid NOT NULL,
    platform text NOT NULL,
    label text,
    openbao_path text NOT NULL,
    status text NOT NULL,
    last_validated_at timestamptz,
    expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX user_credentials_user_platform_idx
    ON user_credentials (user_id, platform, status);

ALTER TABLE sources
    ADD CONSTRAINT sources_credentials_fk
    FOREIGN KEY (credentials_id) REFERENCES user_credentials(id);

ALTER TABLE scraping_jobs
    ADD CONSTRAINT scraping_jobs_credentials_fk
    FOREIGN KEY (credentials_id) REFERENCES user_credentials(id);

CREATE TABLE user_transcription_keys (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    user_id uuid NOT NULL,
    provider text NOT NULL,
    label text,
    openbao_path text NOT NULL,
    status text NOT NULL,
    is_primary boolean DEFAULT false,
    is_fallback boolean DEFAULT false,
    workers_count integer DEFAULT 1 CHECK (workers_count BETWEEN 1 AND 5),
    monthly_cap_usd real,
    current_month_spend_usd real DEFAULT 0,
    current_balance_usd real,
    last_balance_check_at timestamptz,
    last_validated_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX user_transcription_keys_one_primary_per_user
    ON user_transcription_keys (tenant_id, user_id)
    WHERE is_primary = true AND status = 'active';

CREATE INDEX user_transcription_keys_user_idx
    ON user_transcription_keys (user_id, status);

CREATE TABLE github_integrations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    user_id uuid NOT NULL UNIQUE,
    github_login text NOT NULL,
    github_user_id bigint NOT NULL,
    openbao_path text NOT NULL,
    scope text NOT NULL,
    last_validated_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);
