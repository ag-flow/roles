# BUG-23 — `filters` jamais validés : `submit(mode=auto)` invalide bloque la requête en `discovering`

- **Zone** : acquisition / filtres (façade MCP)
- **Fichier(s)** : `backend/src/role_builder/services/acquisition/filters.py:29` (+ `event_handlers.py:83`, `scraper_orchestrator.py:82-84`)
- **Sévérité** : majeure
- **Confiance** : haute
- **Difficulté de correction** : **Opus**

## Problème

Ni l'adaptateur ni le service ne valident `filters`. Deux effets :
1. `select_items(k, filters={"since": "pas-une-date"})` → `ValueError` de `datetime.fromisoformat` non catchée → erreur de transport MCP (idem `max_items` non-entier → erreur asyncpg).
2. Bien pire : `submit_acquisition(mode="auto", filters={"since": "pas-une-date"})` **réussit** (les filters sont stockés en jsonb sans contrôle) ; à l'event `discovered`, `auto_select.on_discovery_complete` → `resolve_item_filters` lève, l'orchestrateur catch tout, marque le job scraping `failed` — et la requête reste stockée `discovering` à vie, aucune sélection, aucun signal au pilote.

## Scénario d'échec

Le pilote soumet en mode auto avec `since: "2026/07/01"` (format non-ISO) → `{request_key, status: "discovering"}` OK, puis pull `request_status` indéfiniment : toujours `discovering`, counts figés, aucune erreur visible.

## Piste de résolution

Valider `filters` au bord (submit + select) via un modèle Pydantic (`max_items: int>0`, dates ISO, durées int) → `AcquisitionError("INVALID_FILTERS", ...)`. Dans `on_discovery_complete`, catcher l'erreur résiduelle et marquer la requête en échec visible (recoupe BUG-19).

## Pourquoi Opus

Un DTO de filtres + branchement aux deux endroits + le sauvetage de la requête bloquée (3e chemin) + tests.

## ✅ Résolu (2026-07-06)

resolve_item_filters lève INVALID_FILTERS (dates ISO, ints positifs/non-négatifs, types) ; validé aussi à la soumission (submit_acquisition) pour rejeter un mode=auto invalide en amont.

Vérifié : suite backend verte (481 passed).
