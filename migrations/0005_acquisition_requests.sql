-- Migration 0005 : modèle de données V2 — requêtes d'acquisition.
-- Référence : docs/specs/v2/01-protocole-mcp.md § 4.
--
-- Introduit le concept de "requête d'acquisition" (ticket asynchrone) qui
-- remplace role_projects comme point de rattachement des sources côté
-- pipeline d'acquisition. Cette migration :
--   1. crée acquisition_requests et corpus_pull_cursors,
--   2. fait évoluer source_items vers le vocabulaire dépôt docflow,
--   3. rétro-crée une acquisition_requests par source existante, à partir
--      de son role_project (rattachement historique), pour que les items
--      déjà scrapés/transcrits restent traçables une fois role_projects
--      et les tables de synthèse purgés (migration 0006).
--
-- role_projects n'est PAS touché par cette migration (table conservée,
-- colonnes obsolètes non retirées) : hors périmètre de ce lot, qui porte
-- uniquement sur le modèle de données V2 côté acquisition. Cf. commit
-- message / discussion pour le lot suivant (purge du code Python +
-- devenir de role_projects).

-- ----------------------------------------------------------------------------
-- Section 1 : acquisition_requests
-- ----------------------------------------------------------------------------

CREATE TABLE acquisition_requests (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    request_key     text NOT NULL UNIQUE,      -- slug lisible
    tenant_id       uuid NOT NULL,
    submitted_by    text NOT NULL,             -- identité passerelle déclarée
    kind            text NOT NULL CHECK (kind IN ('scrape','upload')),
    source_id       uuid REFERENCES sources(id),  -- null si kind=upload pur
    mode            text CHECK (mode IN ('auto','discover_only')),
    filters         jsonb,
    docflow_target  jsonb,                     -- {workspace, block} ou null=convention
    note            text,
    status          text NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX acquisition_requests_tenant_status_idx
    ON acquisition_requests (tenant_id, status);

CREATE INDEX acquisition_requests_submitted_by_idx
    ON acquisition_requests (submitted_by, created_at DESC);

-- ----------------------------------------------------------------------------
-- Section 2 : corpus_pull_cursors
-- ----------------------------------------------------------------------------

CREATE TABLE corpus_pull_cursors (
    request_id   uuid NOT NULL REFERENCES acquisition_requests(id),
    caller       text NOT NULL,
    last_pulled_at timestamptz NOT NULL,
    PRIMARY KEY (request_id, caller)
);

-- ----------------------------------------------------------------------------
-- Section 3 : source_items — colonnes dépôt docflow + statuts révisés
-- ----------------------------------------------------------------------------

ALTER TABLE source_items
    ADD COLUMN docflow_doc_id text,
    ADD COLUMN docflow_slug text,
    ADD COLUMN deposited_at timestamptz,
    ADD COLUMN upload_expires_at timestamptz;

-- Le pipeline devient : ... → transcribed → depositing → deposited.
-- 'chunking'/'indexed' (V1) n'ont plus cours ; on remappe les données
-- existantes vers le nouveau vocabulaire (no-op si aucune ligne concernée).
UPDATE source_items SET status = 'depositing' WHERE status = 'chunking';
UPDATE source_items SET status = 'deposited' WHERE status = 'indexed';

-- ----------------------------------------------------------------------------
-- Section 4 : migration des données — sources.role_project_id → acquisition_requests
-- ----------------------------------------------------------------------------
--
-- Une acquisition_requests rétro-créée par source (pas par projet : le
-- schéma V2 rattache une requête à UNE source). request_key dérivé du nom
-- du role_project, slugifié, suffixé par les 8 premiers caractères de
-- l'id de la source pour garantir l'unicité (plusieurs sources peuvent
-- partager le même role_project / le même nom slugifié).
--
-- submitted_by = 'migration-v1' : ces sources n'ont jamais transité par
-- la passerelle MCP (elle n'existait pas), on trace donc l'origine
-- "migration" plutôt que d'inventer une fausse identité d'appelant.
-- mode = 'auto' : le pipeline V1 ne connaissait pas la sélection en deux
-- temps ; c'est l'équivalent le plus proche.
-- status = 'completed' : ces sources sont un passif déjà traité (sprints
-- 1-8), pas une requête en cours.

WITH slugged AS (
    SELECT
        s.id AS source_id,
        s.tenant_id,
        s.created_at,
        s.updated_at,
        COALESCE(
            NULLIF(
                regexp_replace(
                    regexp_replace(lower(rp.display_name), '[^a-z0-9]+', '-', 'g'),
                    '(^-+|-+$)', '', 'g'
                ),
                ''
            ),
            'legacy'
        ) AS slug_base
    FROM sources s
    JOIN role_projects rp ON rp.id = s.role_project_id
)
INSERT INTO acquisition_requests (
    request_key, tenant_id, submitted_by, kind, source_id, mode,
    filters, docflow_target, note, status, created_at, updated_at
)
SELECT
    'legacy-' || left(slug_base, 40) || '-' || substr(source_id::text, 1, 8),
    tenant_id,
    'migration-v1',
    'scrape',
    source_id,
    'auto',
    NULL,
    NULL,
    'Migration V1 → V2 : rattachée à l''ex role_project via sources.role_project_id.',
    'completed',
    created_at,
    updated_at
FROM slugged;
