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
