# BUG-28 — `list_discovered` : `cursor` non numérique et `limit` négatif non validés

- **Zone** : acquisition / discovery (confirmé par 2 agents)
- **Fichier(s)** : `backend/src/role_builder/services/acquisition/discovery.py:33` et `:36`
- **Sévérité** : mineure
- **Confiance** : haute
- **Difficulté de correction** : **Sonnet**

## Problème

`offset = int(cursor)` lève `ValueError` (non catché — pas un `AcquisitionError`) pour tout cursor non entier ; `limit=-5` produit `LIMIT -4` → `asyncpg.PostgresError`. Dans les deux cas : erreur de transport MCP au lieu de l'enveloppe §5.6. Le `next_cursor` étant une string opaque, un pilote peut légitimement y remettre autre chose.

## Scénario d'échec

`roles__list_discovered(k, cursor="abc")` sur une requête existante → `ToolError « invalid literal for int() with base 10 »`.

## Piste de résolution

Parser `cursor`/`limit` défensivement, lever `AcquisitionError("INVALID_CURSOR", ...)` (rejeter aussi les négatifs), borner `limit` (1..N).

## Pourquoi Sonnet

Parsing défensif localisé + tests.

## ✅ Résolu (2026-07-06)

discovery._parse_cursor/_parse_limit lèvent INVALID_CURSOR/INVALID_LIMIT (offset ≥ 0, limit borné 1..200).

Vérifié : suite backend verte (481 passed).
