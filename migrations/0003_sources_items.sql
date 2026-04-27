-- Migration 0003 : Tables sources et source_items.
-- Référence : docs/specs/01-data-model.md § sources, source_items.

CREATE TABLE sources (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    role_project_id uuid NOT NULL REFERENCES role_projects(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    platform text NOT NULL,
    source_type text NOT NULL,
    url text NOT NULL,
    credentials_id uuid,  -- FK ajoutée en 0006 (user_credentials pas encore créée)
    status text NOT NULL DEFAULT 'pending_discovery',
    discovered_count integer,
    error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX sources_role_project_idx ON sources (role_project_id);

CREATE TABLE source_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id uuid NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    platform_item_id text NOT NULL,
    title text,
    duration_s integer,
    published_at timestamptz,
    thumbnail_url text,
    status text NOT NULL,
    audio_s3_key text,
    transcript_s3_key text,
    selected boolean DEFAULT false,
    error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_id, platform_item_id)
);

CREATE INDEX source_items_source_status_idx ON source_items (source_id, status);
CREATE INDEX source_items_tenant_idx ON source_items (tenant_id);
