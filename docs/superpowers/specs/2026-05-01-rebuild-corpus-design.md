# Re-chunking transcript existant (rebuild corpus) — Design

**Date :** 2026-05-01
**Phase :** 2 (post-MVP, sous-projet E)
**Sprint d'origine :** Sprint 4 (open-decision § corpus indexing)
**Effort :** S (~45 min)

## Objectif

Permettre à un utilisateur de **reconstruire le corpus** d'un projet (drop
tous les chunks + relancer le chunking) sans avoir à re-scraper / re-transcrire.
Utile quand on change la stratégie de chunking ou la dimension d'embeddings.

## Décisions

### Endpoint

`POST /api/role-projects/{project_id}/corpus/rebuild`

- 202 Accepted avec `{deleted_chunks: int, enqueued_jobs: int}`
- 404 si projet inexistant, 403 si pas owner
- Idempotent (safe à re-jouer)

### Algorithme

En 1 transaction asyncpg :
1. `DELETE FROM corpus_chunks WHERE role_project_id = $1` → rowcount
2. `INSERT INTO chunking_jobs (...) SELECT ... FROM source_items si JOIN sources s
   WHERE s.role_project_id = $1 AND si.transcript_s3_key IS NOT NULL`
   → rowcount

Pas de cleanup des `chunking_jobs` historiques (status='done' / 'failed' restent
en DB pour traçabilité).

### Helpers

`db_helpers/corpus_chunks.py` :
- `delete_by_project(role_project_id, *, pool)` → int (rowcount)

`db_helpers/chunking_jobs.py` :
- `enqueue_for_project(role_project_id, *, pool)` → int (rowcount inséré)

Les deux sont appelés dans une transaction wrapper côté route.

### UI

Bouton "Reconstruire le corpus" dans l'onglet Corpus du projet, avec
`window.confirm` (action destructrice). Affiche le résultat
`{deleted_chunks, enqueued_jobs}` dans une notification inline.

## Tests

- `test_db_helpers_corpus_chunks.py` — test `delete_by_project`
- `test_db_helpers_chunking_jobs.py` — test `enqueue_for_project`
- `test_corpus_route.py` — test rebuild : 202 + ownership 404/403
- Frontend : test sur `RebuildCorpusButton.test.tsx`

## Critères

- [ ] 2 nouveaux helpers + tests
- [ ] route POST + tests
- [ ] UI bouton + test
- [ ] backend tests verts (477 → 482+)
- [ ] frontend tests verts (144 → 145+)
- [ ] commit

## Hors-scope

- Streaming de progression chunk-par-chunk (le user attend que le worker re-traite)
- Re-transcription (on garde les transcripts existants, on ne re-chunke que)
- Sélection partielle (rebuild uniquement quelques source_items)
