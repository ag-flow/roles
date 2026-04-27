-- Migration 0008 : Tables du pipeline de synthèse.
-- Référence : docs/specs/01-data-model.md § Section 5.

CREATE TABLE prompts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL UNIQUE,
    type text NOT NULL,
    target_section text,
    description text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE prompt_versions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    prompt_id uuid NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
    version_number integer NOT NULL,
    template text NOT NULL,
    parameters_schema jsonb,
    is_system_default boolean DEFAULT false,
    created_by uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (prompt_id, version_number)
);

CREATE UNIQUE INDEX prompt_versions_one_system_default
    ON prompt_versions (prompt_id)
    WHERE is_system_default = true;

CREATE TABLE runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    role_project_id uuid NOT NULL REFERENCES role_projects(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    prompt_version_id uuid NOT NULL REFERENCES prompt_versions(id),
    input_summary jsonb,
    parameters jsonb,
    instruction_override text,
    status text NOT NULL,
    output text,
    llm_provider text,
    llm_model text,
    tokens_input integer,
    tokens_output integer,
    cost_usd real,
    started_at timestamptz,
    completed_at timestamptz,
    error text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX runs_project_status_idx
    ON runs (role_project_id, status, created_at DESC);

CREATE TABLE signals (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    role_project_id uuid NOT NULL REFERENCES role_projects(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    source_item_id uuid REFERENCES source_items(id),
    source_chunks uuid[],
    type text NOT NULL,
    content jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX signals_project_type_idx ON signals (role_project_id, type);

CREATE TABLE clusters (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    role_project_id uuid NOT NULL REFERENCES role_projects(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    name text NOT NULL,
    description text,
    signal_ids uuid[] NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX clusters_project_idx ON clusters (role_project_id);

CREATE TABLE document_plans (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    role_project_id uuid NOT NULL REFERENCES role_projects(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    section text NOT NULL,
    planned_documents jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX document_plans_project_section_idx
    ON document_plans (role_project_id, section);

CREATE TABLE role_documents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    role_project_id uuid NOT NULL REFERENCES role_projects(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    section text NOT NULL,
    name text NOT NULL,
    content text NOT NULL,
    source_run_id uuid REFERENCES runs(id),
    version integer NOT NULL DEFAULT 1,
    is_current boolean DEFAULT false,
    locked boolean DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX role_documents_current_unique
    ON role_documents (role_project_id, section, name)
    WHERE is_current = true;

CREATE INDEX role_documents_project_idx ON role_documents (role_project_id);
