-- Migration 0006 : purge des tables de synthèse/publication (refonte V2).
-- Référence : docs/specs/v2/01-protocole-mcp.md § 4 "Supprimées",
-- docs/specs/OBSOLETE.md.
--
-- ⚠️ Destructif. Ne jamais appliquer sans avoir au préalable exécuté
-- scripts/archive_v1_tables.sh (dump pg_dump --table de ces tables dans
-- archive/). Migration séparée de 0005 exprès : 0005 est repris de manière
-- sûre à tout moment (ajouts + migration de données), 0006 est le point
-- de non-retour.
--
-- Ordre de suppression : dépendants avant leurs référencés (FK sans
-- ON DELETE CASCADE pour la plupart de ces tables), pour ne pas dépendre
-- d'un DROP ... CASCADE qui masquerait les dépendances réelles.

-- La vue agrégée référence corpus_chunks et role_documents (colonnes
-- chunks_count / documents_count / items_indexed) : obsolète de fait,
-- purgée avec les tables qu'elle agrège.
DROP VIEW IF EXISTS v_role_project_summary;

DROP TABLE IF EXISTS corpus_chunks;
DROP TABLE IF EXISTS chunking_jobs;

DROP TABLE IF EXISTS signals;
DROP TABLE IF EXISTS clusters;
DROP TABLE IF EXISTS document_plans;
DROP TABLE IF EXISTS role_documents;
DROP TABLE IF EXISTS runs;

DROP TABLE IF EXISTS prompt_versions;
DROP TABLE IF EXISTS prompts;

DROP TABLE IF EXISTS role_publications;
DROP TABLE IF EXISTS role_publication_config;

DROP TABLE IF EXISTS github_integrations;
DROP TABLE IF EXISTS oauth_states;
