# BUG-15 — Pagination `list_discovered` instable : doublons et pertes d'items entre pages

- **Zone** : acquisition / db helpers (confirmé par 2 agents)
- **Fichier(s)** : `backend/src/role_builder/db_helpers/source_items.py:181` (consommé par `services/acquisition/discovery.py:33-48`)
- **Sévérité** : majeure
- **Confiance** : haute
- **Difficulté de correction** : **Sonnet**

## Problème

`ORDER BY published_at DESC NULLS LAST` sans tie-breaker + pagination OFFSET. PostgreSQL ne garantit aucun ordre entre lignes ex æquo, et les ex æquo sont la norme : yt-dlp fournit souvent des dates à précision jour (toute une chaîne au même timestamp), et les items upload ont `published_at NULL`. Deux appels paginés successifs peuvent réordonner les ex æquo (d'autant qu'`updated_at` est touché par la sélection ou les changements de statut concurrents) → un item apparaît sur deux pages, un autre n'apparaît jamais.

## Scénario d'échec

Chaîne YouTube de 120 vidéos publiées le même jour ; le pilote pagine par 50 via `list_discovered` pour choisir quoi sélectionner → certaines vidéos sont invisibles, jamais sélectionnables. Même effet sur `resolve_item_ids_from_filters` avec `max_items` (le sous-ensemble retenu est non déterministe).

## Piste de résolution

Ajouter un tie-breaker stable (`ORDER BY published_at DESC NULLS LAST, id ASC`) dans `list_items_by_source` (et `list_by_project`). Idéalement, curseur keyset plutôt qu'OFFSET.

## Pourquoi Sonnet

Le tie-breaker est une ligne (le passage à un curseur keyset serait Opus, mais non requis pour corriger le bug).

## ✅ Résolu (2026-07-06)

tie-breaker id ASC ajouté aux ORDER BY published_at (list_items_by_source, list_by_project) : pagination stable.

Vérifié : suite backend verte (481 passed).
