# BUG-62 — Migration 0001 exige l'extension `vector` alors que la V2 l'a abandonnée

- **Zone** : infra / migrations
- **Fichier(s)** : `migrations/0001_initial_schema.sql:23-25` (+ `corpus_chunks … vector(1024)` l.114) ; contradiction avec `backend/src/role_builder/migrations.py:13-14` (« Aucun CREATE EXTENSION dans les SQL ») et CLAUDE.md (« pgvector plus requis en V2 »)
- **Sévérité** : mineure
- **Confiance** : haute
- **Difficulté de correction** : **Opus**

## Problème

Toute DB neuve doit rejouer 0001 → 0010 ; 0001 crée `corpus_chunks` avec une colonne `vector(1024)` et un index ivfflat (détruits ensuite par 0006). Un PostgreSQL 16 sans les binaires pgvector installés échoue au `CREATE EXTENSION "vector"` (l'`IF NOT EXISTS` ne protège que si l'extension existe déjà) → backend en crash loop au premier boot.

## Scénario d'échec

Provisioning V2 « propre » sur un Postgres managé sans pgvector (conforme à la doc V2 qui dit ne plus en avoir besoin) → la stack ne démarre jamais.

## Piste de résolution

Soit documenter pgvector comme prérequis d'installation tant que 0001 n'est pas re-compacté, soit re-compacter le socle (0001 sans les tables de synthèse/pgvector) pour les installations neuves — en gardant la chaîne actuelle pour les DB existantes via `schema_migrations`.

## Pourquoi Opus

Le re-compactage de migration est une opération délicate à synchroniser avec les DB déjà migrées (risque de divergence de `schema_migrations`).

## ✅ Résolu (2026-07-06)

Dépendance pgvector supprimée : migration 0001 ne crée plus l'extension `vector`, ni la colonne `embedding vector(1024)`, ni l'index ivfflat. La table `corpus_chunks` (droppée par 0006 de toute façon) est conservée sans le vecteur. Une base neuve n'exige donc plus un Postgres avec pgvector.

Résidu fonctionnel associé nettoyé en même temps (hors des 62 bugs initiaux) : le worker de transcription (`docker/transcription-worker/`) ne fait plus le handoff chunking pgvector (`insert_chunking_job`/`lookup_role_project_for_item` supprimés).

Vérifié : `test_migrations.py` applique 0001→0010 sur une base éphémère SANS extension vector (481 passed backend, 33 passed worker).
