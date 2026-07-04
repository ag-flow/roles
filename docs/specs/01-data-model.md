> ℹ️ **Conservée avec adaptations V2 (2026-07-04).** Cœur conservé (sources, items, queues, credentials, workers). Supprimées : tables synthèse/publication/pgvector. role_projects → acquisition_requests (v2/01 §4).
> Voir `docs/specs/v2/00-fondations-v2.md` et `docs/specs/v2/01-protocole-mcp.md`.

# 01 — Modèle de données (référence SQL transverse)

> Ce document est la **référence canonique** du schéma de données. Tous les
> autres fichiers de la spec font référence aux tables et colonnes définies
> ici. À consulter avant et pendant l'implémentation de tout autre bloc.

## Conventions

- Tous les IDs sont des `uuid` (extension `uuid-ossp` ou `pgcrypto`)
- Toutes les dates sont des `timestamptz` (UTC)
- Tous les schémas portent un `tenant_id` (multi-tenant ready dès le départ)
- Indentation : 4 espaces dans les fichiers SQL
- Pas d'Alembic : fichiers SQL versionnés à la main dans `migrations/NNNN_description.sql`
- Triggers PG NOTIFY pour les événements temps réel (cf. § Triggers)

## Extensions PostgreSQL requises

```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";  -- pgvector pour les embeddings
```

## Section 1 — Tables principales (corpus)

### `role_projects`

Un projet de rôle = un rôle ag.flow en construction côté Role Builder.

```sql
CREATE TABLE role_projects (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    user_id uuid NOT NULL,
    display_name text NOT NULL,
    description text,
    target_role_id text,            -- id du rôle dans ag.flow (si déjà créé)
    identity text,                  -- markdown produit par identity_synthesizer
    global_directives text,         -- remarques utilisateur niveau projet
    language text,                  -- override de la langue par défaut (ex: 'fr')
    mistral_secret_ref text,        -- référence au secret ag.flow pour Mistral
    is_public boolean DEFAULT false,
    keep_audio boolean DEFAULT true, -- conserver les audios bruts après transcription
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX role_projects_tenant_user_idx ON role_projects (tenant_id, user_id);
```

### `sources`

Une source = une URL fournie par l'utilisateur (chaîne, playlist, vidéo unique).

```sql
CREATE TABLE sources (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    role_project_id uuid NOT NULL REFERENCES role_projects(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    platform text NOT NULL,         -- youtube|instagram|tiktok|upload
    source_type text NOT NULL,      -- single|channel|playlist|account
    url text NOT NULL,
    credentials_id uuid REFERENCES user_credentials(id),
    status text NOT NULL DEFAULT 'pending_discovery',
                                    -- pending_discovery|discovering|discovered|failed
    discovered_count integer,        -- rempli après discover
    error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX sources_role_project_idx ON sources (role_project_id);
```

### `source_items`

Un item = une vidéo découverte ou ingérée d'une source.

```sql
CREATE TABLE source_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id uuid NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    platform_item_id text NOT NULL, -- ID natif (video_id YouTube, etc.)
    title text,
    duration_s integer,
    published_at timestamptz,
    thumbnail_url text,
    status text NOT NULL,           -- voir § États ci-dessous
    audio_s3_key text,
    transcript_s3_key text,
    selected boolean DEFAULT false, -- l'user a sélectionné cet item pour ingestion
    error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_id, platform_item_id)
);

CREATE INDEX source_items_source_status_idx ON source_items (source_id, status);
CREATE INDEX source_items_tenant_idx ON source_items (tenant_id);
```

#### États possibles d'un `source_items.status`

```
pending_download
    ↓
downloading
    ↓
audio_ready          ← audio dans MinIO
    ↓
queued_transcription
    ↓
transcribing
    ↓
transcribed          ← transcript dans MinIO
    ↓
chunking
    ↓
indexed              ← chunks dans pgvector, prêt pour analyses

(à toute étape) → failed (avec error rempli)
```

### `corpus_chunks`

Chunks de texte indexés avec embedding pour la recherche sémantique.

```sql
CREATE TABLE corpus_chunks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_item_id uuid NOT NULL REFERENCES source_items(id) ON DELETE CASCADE,
    role_project_id uuid NOT NULL REFERENCES role_projects(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    chunk_index integer NOT NULL,
    start_s real,                   -- timestamp début dans l'audio
    end_s real,                     -- timestamp fin dans l'audio
    text text NOT NULL,
    embedding vector(1536),         -- dimension à confirmer selon modèle d'embedding
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX corpus_chunks_embedding_idx
    ON corpus_chunks USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX corpus_chunks_role_project_idx ON corpus_chunks (role_project_id);
```

## Section 2 — Tables des queues

### `scraping_jobs`

```sql
CREATE TABLE scraping_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id uuid NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    source_item_id uuid REFERENCES source_items(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    credentials_id uuid REFERENCES user_credentials(id),
    command text NOT NULL,          -- discover | download
    status text NOT NULL,           -- pending|claimed|processing|done|failed
    priority integer DEFAULT 0,
    claimed_by text,                -- identifiant du worker/processus
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
```

### `transcription_jobs`

```sql
CREATE TABLE transcription_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_item_id uuid NOT NULL REFERENCES source_items(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    audio_s3_key text NOT NULL,
    language text,                  -- ou null = auto-detect
    worker_pool_id text NOT NULL,   -- shared_default | user_{user_id}
    status text NOT NULL,           -- pending|claimed|processing|done|failed
    priority integer DEFAULT 0,
    claimed_by text,
    claimed_at timestamptz,
    started_at timestamptz,
    completed_at timestamptz,
    attempts integer DEFAULT 0,
    max_attempts integer DEFAULT 3,
    provider_used text,             -- faster-whisper|deepgram|assemblyai|...
    cost_estimate_usd real,
    cost_actual_usd real,
    error text,
    error_history jsonb DEFAULT '[]'::jsonb,  -- liste des erreurs précédentes
    result_s3_key text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX transcription_jobs_pool_status_idx
    ON transcription_jobs (worker_pool_id, status, created_at);
```

### `chunking_jobs`

Queue dédiée pour le chunking + embedding (étape post-transcription).

```sql
CREATE TABLE chunking_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_item_id uuid NOT NULL REFERENCES source_items(id) ON DELETE CASCADE,
    role_project_id uuid NOT NULL REFERENCES role_projects(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    transcript_s3_key text NOT NULL,
    status text NOT NULL,           -- pending|claimed|processing|done|failed
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
```

## Section 3 — Tables des credentials et clés API

### `user_credentials` (cookies de scraping)

```sql
CREATE TABLE user_credentials (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    user_id uuid NOT NULL,
    platform text NOT NULL,         -- youtube|instagram|tiktok
    label text,                     -- libellé personnalisable user
    openbao_path text NOT NULL,     -- secret/scraping-credentials/...
    status text NOT NULL,           -- active|expired|invalid|revoked
    last_validated_at timestamptz,
    expires_at timestamptz,         -- si connu
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX user_credentials_user_platform_idx
    ON user_credentials (user_id, platform, status);
```

### `user_transcription_keys` (clés API SaaS de transcription)

```sql
CREATE TABLE user_transcription_keys (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    user_id uuid NOT NULL,
    provider text NOT NULL,         -- deepgram|assemblyai|openai-whisper|speechmatics
    label text,
    openbao_path text NOT NULL,     -- secret/transcription-keys/...
    status text NOT NULL,           -- active|low|exhausted|invalid
    is_primary boolean DEFAULT false,
    is_fallback boolean DEFAULT false,
    workers_count integer DEFAULT 1 CHECK (workers_count BETWEEN 1 AND 5),
    monthly_cap_usd real,
    current_month_spend_usd real DEFAULT 0,
    current_balance_usd real,       -- si polling supporté
    last_balance_check_at timestamptz,
    last_validated_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Un seul "primary" par user
CREATE UNIQUE INDEX user_transcription_keys_one_primary_per_user
    ON user_transcription_keys (tenant_id, user_id)
    WHERE is_primary = true AND status = 'active';

CREATE INDEX user_transcription_keys_user_idx
    ON user_transcription_keys (user_id, status);
```

### `github_integrations` (OAuth GitHub)

```sql
CREATE TABLE github_integrations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    user_id uuid NOT NULL UNIQUE,
    github_login text NOT NULL,
    github_user_id bigint NOT NULL,
    openbao_path text NOT NULL,     -- secret/github-tokens/...
    scope text NOT NULL,
    last_validated_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);
```

### `role_publication_config`

```sql
CREATE TABLE role_publication_config (
    role_project_id uuid PRIMARY KEY REFERENCES role_projects(id) ON DELETE CASCADE,
    repo_full_name text NOT NULL,   -- "user/repo"
    target_subdirectory text NOT NULL, -- ex: "roles/ux-clea"
    branch text DEFAULT 'main',
    commit_message_template text DEFAULT 'Update role {role_name}',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
```

### `role_publications` (historique)

```sql
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
```

## Section 4 — Tables de gestion des workers

### `transcription_workers`

État des workers de transcription (containers Docker).

```sql
CREATE TABLE transcription_workers (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    worker_pool_id text NOT NULL,   -- shared_default | user_{user_id}
    container_id text,              -- Docker container ID
    container_name text,
    provider text,                  -- faster-whisper|deepgram|assemblyai|...
    status text NOT NULL,           -- starting|idle|busy|stopping|stopped
    last_activity_at timestamptz,
    started_at timestamptz NOT NULL DEFAULT now(),
    stopped_at timestamptz,
    host text                       -- pve1|pve2
);

CREATE INDEX transcription_workers_pool_status_idx
    ON transcription_workers (worker_pool_id, status);
CREATE INDEX transcription_workers_idle_idx
    ON transcription_workers (last_activity_at)
    WHERE status = 'idle';
```

## Section 5 — Tables du pipeline de synthèse

### `prompts` (bibliothèque globale partagée)

```sql
CREATE TABLE prompts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL UNIQUE,
    type text NOT NULL,             -- extractor|clusterer|decomposer|writer|identity
    target_section text,            -- pour les writers, section cible suggérée
    description text,
    created_at timestamptz NOT NULL DEFAULT now()
);
```

### `prompt_versions`

```sql
CREATE TABLE prompt_versions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    prompt_id uuid NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
    version_number integer NOT NULL,
    template text NOT NULL,
    parameters_schema jsonb,
    is_system_default boolean DEFAULT false,
    created_by uuid,                -- user_id, null si system
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (prompt_id, version_number)
);

-- Une seule version system_default active par prompt
CREATE UNIQUE INDEX prompt_versions_one_system_default
    ON prompt_versions (prompt_id)
    WHERE is_system_default = true;
```

### `runs`

Un run = une exécution d'une version de prompt sur un set d'inputs.

```sql
CREATE TABLE runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    role_project_id uuid NOT NULL REFERENCES role_projects(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    prompt_version_id uuid NOT NULL REFERENCES prompt_versions(id),
    input_summary jsonb,            -- ce qu'on a donné en entrée (refs)
    parameters jsonb,
    instruction_override text,      -- remarque user ponctuelle pour ce run
    status text NOT NULL,           -- pending|running|done|failed
    output text,                    -- markdown ou JSON sérialisé selon le type
    llm_provider text,              -- mistral
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
```

### `signals` (output des extractors)

```sql
CREATE TABLE signals (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    role_project_id uuid NOT NULL REFERENCES role_projects(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    source_item_id uuid REFERENCES source_items(id),
    source_chunks uuid[],           -- références aux chunks utilisés (pour traçabilité)
    type text NOT NULL,             -- heuristique|anecdote|vocab|cadre|opinion
    content jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX signals_project_type_idx ON signals (role_project_id, type);
```

### `clusters` (output des clusterers)

```sql
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
```

### `document_plans` (output des decomposers)

```sql
CREATE TABLE document_plans (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    role_project_id uuid NOT NULL REFERENCES role_projects(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    section text NOT NULL,          -- Role|Missions|Skills|custom-name
    planned_documents jsonb NOT NULL, -- array de {name, brief, supporting_signals}
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX document_plans_project_section_idx
    ON document_plans (role_project_id, section);
```

### `role_documents` (documents finaux du rôle)

```sql
CREATE TABLE role_documents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    role_project_id uuid NOT NULL REFERENCES role_projects(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    section text NOT NULL,          -- Role|Missions|Skills|custom-name
    name text NOT NULL,             -- nom du document (ex: "user-research-interviews")
    content text NOT NULL,          -- markdown
    source_run_id uuid REFERENCES runs(id),
    version integer NOT NULL DEFAULT 1,
    is_current boolean DEFAULT false,
    locked boolean DEFAULT false,   -- édité manuellement par l'user, ne pas régénérer
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Un seul document "current" par (project, section, name)
CREATE UNIQUE INDEX role_documents_current_unique
    ON role_documents (role_project_id, section, name)
    WHERE is_current = true;

CREATE INDEX role_documents_project_idx ON role_documents (role_project_id);
```

## Section 6 — Triggers PG NOTIFY pour temps réel

Le backend FastAPI maintient un WebSocket par client. Quand un état important
change en base, on émet un PG NOTIFY que le backend relaie au front.

### Pattern général

```sql
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
```

### Triggers à installer

```sql
-- source_items : changements d'état visibles dans l'UI
CREATE TRIGGER source_items_notify
    AFTER UPDATE OF status ON source_items
    FOR EACH ROW
    WHEN (OLD.status IS DISTINCT FROM NEW.status)
    EXECUTE FUNCTION notify_event('source_items_changes');

-- runs : suivi de l'exécution des prompts
CREATE TRIGGER runs_notify
    AFTER INSERT OR UPDATE OF status ON runs
    FOR EACH ROW
    EXECUTE FUNCTION notify_event('runs_changes');

-- transcription_workers : démarrage/arrêt des workers
CREATE TRIGGER workers_notify
    AFTER UPDATE OF status ON transcription_workers
    FOR EACH ROW
    EXECUTE FUNCTION notify_event('workers_changes');

-- user_transcription_keys : alertes (low/exhausted)
CREATE TRIGGER keys_notify
    AFTER UPDATE OF status ON user_transcription_keys
    FOR EACH ROW
    WHEN (OLD.status IS DISTINCT FROM NEW.status)
    EXECUTE FUNCTION notify_event('keys_changes');
```

## Section 7 — Vues utiles (optionnel mais recommandé)

### `v_role_project_summary`

Vue agrégée pour les listes de projets dans l'UI :

```sql
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
```

## Section 8 — Conventions de nommage des champs

| Suffixe | Sens | Exemple |
|---------|------|---------|
| `_id` | Référence FK ou ID externe | `tenant_id`, `target_role_id` |
| `_at` | Timestamp | `created_at`, `claimed_at` |
| `_s` | Durée en secondes (real) | `duration_s`, `start_s` |
| `_usd` | Montant en USD | `cost_usd`, `monthly_cap_usd` |
| `_s3_key` | Clé d'objet MinIO/S3 | `audio_s3_key` |
| `_path` | Chemin OpenBao | `openbao_path` |
| `_count` | Compteur entier | `attempts`, `workers_count` |

## Section 9 — Patterns de queue (à utiliser partout)

Pattern standard pour pull une tâche dans une queue :

```sql
SELECT * FROM <queue_table>
WHERE status = 'pending'
  AND <filtres spécifiques au worker>
ORDER BY priority DESC, created_at ASC
FOR UPDATE SKIP LOCKED
LIMIT 1;
```

`FOR UPDATE SKIP LOCKED` garantit que plusieurs workers concurrents ne se
marchent pas dessus.

Une fois la tâche claim :

```sql
UPDATE <queue_table>
SET status = 'claimed',
    claimed_by = $worker_id,
    claimed_at = now(),
    attempts = attempts + 1
WHERE id = $job_id;
```

## TODO du fichier (à trancher pendant l'implémentation)

- [ ] Confirmer la dimension exacte des embeddings (1536 pour OpenAI
      text-embedding-3-small, autre pour Mistral). Cf. § 06 pour le choix
      du modèle.
- [ ] Décider si on ajoute des soft-deletes (`deleted_at`) sur certaines
      tables ou si la suppression est toujours hard (CASCADE actuel).
- [ ] Définir les politiques de rétention : combien de temps garde-t-on
      les `runs` archivés, les transcripts, les audios bruts ?

---

**Document précédent :** `00-overview.md`
**Document suivant :** `02-foundations.md`
