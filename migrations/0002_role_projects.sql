-- Migration 0002 : Table role_projects.
-- Référence : docs/specs/01-data-model.md § role_projects.

CREATE TABLE role_projects (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    user_id uuid NOT NULL,
    display_name text NOT NULL,
    description text,
    target_role_id text,
    identity text,
    global_directives text,
    language text,
    mistral_secret_ref text,
    is_public boolean DEFAULT false,
    keep_audio boolean DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX role_projects_tenant_user_idx ON role_projects (tenant_id, user_id);
