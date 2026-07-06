# BUG-05 — `published_at` chaîne ISO → colonne timestamptz : DataError, découverte en échec

- **Zone** : services cœur / event handlers
- **Fichier(s)** : `backend/src/role_builder/services/event_handlers.py:64-69`, croisé avec `db_helpers/source_items.py:15-58` et `docker/scrapers/youtube/youtube/discover.py:11-16`
- **Sévérité** : majeure
- **Confiance** : haute
- **Difficulté de correction** : **Sonnet**

## Problème

Le scraper émet `published_at` comme chaîne ISO8601 (`"2023-05-01T00:00:00Z"`, cf. `_format_published_at`). `handle_scraper_event` passe les items tels quels à `insert_source_items_bulk`, qui les bind via `executemany` sur la colonne `published_at timestamptz`. asyncpg n'accepte pas les `str` pour `timestamptz` (pas de codec custom dans `db.py`) → `DataError: expected a datetime.date or datetime.datetime instance, got 'str'`.

## Scénario d'échec

Job `discover` sur une source dont yt-dlp renvoie `upload_date` en mode flat-playlist (fréquent sur les playlists) → l'insert bulk lève → exception remontée dans `process_one_job` → job marqué `failed`, aucun item inséré. Les tests DB passent car ils utilisent des objets `datetime` (`test_db_helpers_source_items.py:81`), pas le flux réel.

## Piste de résolution

Parser `published_at` (`datetime.fromisoformat` avec gestion du suffixe `Z`) dans `event_handlers` ou `insert_source_items_bulk` avant le bind. Ajouter un test avec un item au format event réel (chaîne ISO).

## Pourquoi Sonnet

Conversion localisée + un test avec le format réel.

## ✅ Résolu (2026-07-06)

event_handlers._normalize_item convertit published_at ISO (avec Z) en datetime avant l'insert bulk ; valeur invalide → None + warning.

Vérifié : suite backend verte (481 passed).
