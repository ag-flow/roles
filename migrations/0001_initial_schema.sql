-- ============================================================================
-- Migration 0001 : Schema initial complet (compactage 0001 → 0016)
-- ============================================================================
--
-- Ce fichier consolide en une seule migration les 16 anciennes migrations
-- atomiques générées au fil des sprints 1 → 8 et de la Phase 2 (sous-projets
-- C, D, G). Le contenu est syntaxiquement équivalent : les CREATE TABLE et
-- ALTER TABLE des migrations atomiques ont été préservés mot pour mot.
--
-- Pourquoi compacter :
--   - Sur DB neuve, le runner appliquait 16 fichiers en boucle. Désormais
--     une seule transaction.
--   - Plus simple à diffuser sur un Postgres managé : 1 fichier à fournir
--     à l'admin DB s'il préfère pré-charger le schéma.
--
-- Extensions PostgreSQL :
--   uuid-ossp / pgcrypto / vector. Le `IF NOT EXISTS` rend l'opération
--   idempotente : no-op si l'admin DB a déjà créé les extensions en amont
--   (cf. install.sh --setup-db du repo ag-flow/Configurations). En docker
--   compose local, le user `rb` est superuser de la DB role_builder donc
--   les CREATE EXTENSION fonctionnent ici.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

-- ----------------------------------------------------------------------------
-- Section ex-0002 : role_projects
-- ----------------------------------------------------------------------------

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

-- ----------------------------------------------------------------------------
-- Section ex-0003 : sources_items
-- ----------------------------------------------------------------------------
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

-- ----------------------------------------------------------------------------
-- Section ex-0004 : corpus_chunks
-- ----------------------------------------------------------------------------
-- Migration 0004 : Table corpus_chunks (chunks indexés via pgvector).
-- Référence : docs/specs/01-data-model.md § corpus_chunks.
-- Dimension vecteur 1024 = Mistral Embed (à confirmer Sprint 4).

CREATE TABLE corpus_chunks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_item_id uuid NOT NULL REFERENCES source_items(id) ON DELETE CASCADE,
    role_project_id uuid NOT NULL REFERENCES role_projects(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    chunk_index integer NOT NULL,
    start_s real,
    end_s real,
    text text NOT NULL,
    embedding vector(1024),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX corpus_chunks_role_project_idx ON corpus_chunks (role_project_id);

-- L'index ivfflat est inefficace tant qu'il y a peu de lignes.
-- À créer ou recréer (REINDEX) après ingestion d'un premier corpus.
CREATE INDEX corpus_chunks_embedding_idx
    ON corpus_chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- ----------------------------------------------------------------------------
-- Section ex-0005 : queues
-- ----------------------------------------------------------------------------
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

-- ----------------------------------------------------------------------------
-- Section ex-0006 : credentials_keys
-- ----------------------------------------------------------------------------
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

-- ----------------------------------------------------------------------------
-- Section ex-0007 : workers
-- ----------------------------------------------------------------------------
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

-- ----------------------------------------------------------------------------
-- Section ex-0008 : synthesis
-- ----------------------------------------------------------------------------
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

-- ----------------------------------------------------------------------------
-- Section ex-0009 : publication
-- ----------------------------------------------------------------------------
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

-- ----------------------------------------------------------------------------
-- Section ex-0010 : triggers
-- ----------------------------------------------------------------------------
-- Migration 0010 : Fonction notify_event + triggers PG NOTIFY.
-- Référence : docs/specs/01-data-model.md § Section 6.

CREATE OR REPLACE FUNCTION notify_event() RETURNS trigger AS $$
DECLARE
    channel text;
    payload jsonb;
BEGIN
    channel := TG_ARGV[0];
    payload := jsonb_build_object(
        'table', TG_TABLE_NAME,
        'op', TG_OP,
        'tenant_id', NEW.tenant_id,
        'id', NEW.id,
        'status', NEW.status
    );
    PERFORM pg_notify(channel, payload::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER source_items_notify
    AFTER UPDATE OF status ON source_items
    FOR EACH ROW
    WHEN (OLD.status IS DISTINCT FROM NEW.status)
    EXECUTE FUNCTION notify_event('source_items_changes');

CREATE TRIGGER runs_notify
    AFTER INSERT OR UPDATE OF status ON runs
    FOR EACH ROW
    EXECUTE FUNCTION notify_event('runs_changes');

CREATE TRIGGER workers_notify
    AFTER UPDATE OF status ON transcription_workers
    FOR EACH ROW
    EXECUTE FUNCTION notify_event('workers_changes');

CREATE TRIGGER keys_notify
    AFTER UPDATE OF status ON user_transcription_keys
    FOR EACH ROW
    WHEN (OLD.status IS DISTINCT FROM NEW.status)
    EXECUTE FUNCTION notify_event('keys_changes');

-- ----------------------------------------------------------------------------
-- Section ex-0011 : views
-- ----------------------------------------------------------------------------
-- Migration 0011 : Vues utiles pour l'UI.
-- Référence : docs/specs/01-data-model.md § Section 7.

CREATE VIEW v_role_project_summary AS
SELECT
    rp.id,
    rp.tenant_id,
    rp.user_id,
    rp.display_name,
    rp.description,
    rp.is_public,
    rp.created_at,
    rp.updated_at,
    COUNT(DISTINCT s.id) AS sources_count,
    COUNT(DISTINCT si.id) FILTER (WHERE si.status = 'indexed') AS items_indexed,
    COUNT(DISTINCT si.id) AS items_total,
    COUNT(DISTINCT cc.id) AS chunks_count,
    COUNT(DISTINCT rd.id) FILTER (WHERE rd.is_current) AS documents_count,
    rp.target_role_id IS NOT NULL AS pushed_to_agflow
FROM role_projects rp
LEFT JOIN sources s ON s.role_project_id = rp.id
LEFT JOIN source_items si ON si.source_id = s.id
LEFT JOIN corpus_chunks cc ON cc.role_project_id = rp.id
LEFT JOIN role_documents rd ON rd.role_project_id = rp.id
GROUP BY rp.id;

-- ----------------------------------------------------------------------------
-- Section ex-0012 : oauth_states
-- ----------------------------------------------------------------------------
-- Migration 0012 : table temporaire pour le state CSRF du flow OAuth GitHub.
-- Sprint 8.
--
-- Le state est généré au démarrage du flow (POST /auth/github/start), inséré
-- ici avec un expires_at (~10 min), puis consommé atomiquement (DELETE
-- ... RETURNING) au callback GitHub. Cleanup auto des entrées expirées via
-- helper `oauth_states.cleanup_expired` (pas de pg_cron — appelé à la
-- demande ou par un job de maintenance).

CREATE TABLE oauth_states (
    state text PRIMARY KEY,
    user_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    provider text NOT NULL DEFAULT 'github',
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL
);

CREATE INDEX oauth_states_expires_idx ON oauth_states (expires_at);

-- ----------------------------------------------------------------------------
-- Section ex-0013 : add_license_to_publication_config
-- ----------------------------------------------------------------------------
-- Migration 0013 : ajout du choix de licence par projet pour la publication
-- GitHub. Sprint 8.
--
-- Valeurs attendues : 'none' / 'polyform-nc' / 'cc-by-nc-sa-4.0' /
-- 'cc-by-4.0' / 'mit'. Pas de CHECK contrainte (validation côté Pydantic
-- via Literal — permet d'ajouter de nouveaux choix sans migration DB).

ALTER TABLE role_publication_config
    ADD COLUMN license_choice text DEFAULT 'none' NOT NULL;

-- ----------------------------------------------------------------------------
-- Section ex-0014 : runs_is_obsolete
-- ----------------------------------------------------------------------------
-- Migration 0014 : marqueur d'obsolescence des runs.
-- Phase 2 sous-projet C.
--
-- Un run devient obsolete (is_obsolete=true) quand un paramètre qui le
-- régit a été modifié après son exécution :
-- 1. role_projects.global_directives édité → tous les runs du projet
-- 2. prompt.set_system_default(prompt_id, new_version_id) → runs du
--    projet utilisant une autre version de ce prompt
--
-- Le drapeau est monotone (true → reste true). Le run reste lisible/
-- téléchargeable, l'obsolescence n'est pas une suppression.

ALTER TABLE runs ADD COLUMN is_obsolete boolean NOT NULL DEFAULT false;

-- Index partial : accélère le listing "runs actifs" si une UI filtre.
CREATE INDEX runs_obsolete_idx
    ON runs (role_project_id, is_obsolete)
    WHERE is_obsolete = false;

-- ----------------------------------------------------------------------------
-- Section ex-0015 : github_integrations_multi_accounts
-- ----------------------------------------------------------------------------
-- Migration 0015 : multi-comptes GitHub par user.
-- Phase 2 sous-projet D.
--
-- Permet à un user de connecter plusieurs comptes GitHub (perso + orga
-- typiquement). La contrainte UNIQUE(user_id) est remplacée par
-- UNIQUE(user_id, github_user_id) — l'unicité est désormais sur le
-- couple (qui se connecte, quel compte GitHub) au lieu de juste qui se
-- connecte.

ALTER TABLE github_integrations
    DROP CONSTRAINT IF EXISTS github_integrations_user_id_key;

ALTER TABLE github_integrations
    ADD CONSTRAINT github_integrations_user_id_github_user_id_key
        UNIQUE (user_id, github_user_id);

-- ----------------------------------------------------------------------------
-- Section ex-0016 : role_projects_custom_sections
-- ----------------------------------------------------------------------------
-- Migration 0016 : sections custom par projet.
-- Phase 2 sous-projet G.
--
-- Tableau JSON de noms de sections, en plus des 3 standards (Role,
-- Missions, Skills). Le decomposer prompt étend son plan de documents à
-- ces sections supplémentaires. Bornage côté API : 0 à 5 sections.
--
-- Format : ["Outils", "Style-redactionnel"]

ALTER TABLE role_projects
    ADD COLUMN custom_sections jsonb NOT NULL DEFAULT '[]'::jsonb;
