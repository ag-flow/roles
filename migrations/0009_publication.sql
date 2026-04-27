-- Migration 0009 : Tables de publication GitHub.
-- Référence : docs/specs/01-data-model.md § role_publication_config, role_publications.

CREATE TABLE role_publication_config (
    role_project_id uuid PRIMARY KEY REFERENCES role_projects(id) ON DELETE CASCADE,
    repo_full_name text NOT NULL,
    target_subdirectory text NOT NULL,
    branch text DEFAULT 'main',
    commit_message_template text DEFAULT 'Update role {role_name}',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE role_publications (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    role_project_id uuid NOT NULL REFERENCES role_projects(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    user_id uuid NOT NULL,
    commit_sha text NOT NULL,
    published_at timestamptz NOT NULL DEFAULT now(),
    files_count integer,
    summary text
);

CREATE INDEX role_publications_project_idx
    ON role_publications (role_project_id, published_at DESC);
