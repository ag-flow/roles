# BUG-25 — Curseur `get_corpus` : l'upsert peut reculer le curseur, `next_cursor` perdu en mode serveur

- **Zone** : façade MCP / corpus / curseurs
- **Fichier(s)** : `backend/src/role_builder/db_helpers/corpus_pull_cursors.py:29-38` ; `services/acquisition/corpus.py:70-79`
- **Sévérité** : mineure
- **Confiance** : moyenne
- **Difficulté de correction** : **Sonnet**

## Problème

1. `ON CONFLICT ... DO UPDATE SET last_pulled_at = EXCLUDED.last_pulled_at` est inconditionnel : deux pulls quasi simultanés du même `caller` peuvent commiter dans l'ordre inverse et faire **reculer** le curseur → le pull `only_new` suivant re-sert des documents déjà vus (doublons pour le pilote).
2. `next_cursor` renvoie `latest.isoformat() if latest else cursor` : en mode curseur serveur sans nouveaux items, il renvoie `null` alors qu'un curseur stocké existe — un client qui alterne mode serveur/stateless perd sa position.

## Scénario d'échec

Pilote avec deux fils d'exécution (ou retry réseau de la passerelle rejouant le POST) pullant `only_new` en parallèle → curseur reculé → documents dupliqués dans la synthèse.

## Piste de résolution

`DO UPDATE SET last_pulled_at = GREATEST(corpus_pull_cursors.last_pulled_at, EXCLUDED.last_pulled_at)` ; et renvoyer le curseur stocké dans `next_cursor` quand `latest` est None.

## Pourquoi Sonnet

Un `GREATEST` dans l'upsert + un fallback sur `next_cursor`.

## ✅ Résolu (2026-07-06)

upsert_cursor utilise GREATEST (le curseur ne recule plus) ; next_cursor renvoie la position stockée en mode serveur sans nouveaux items.

Vérifié : suite backend verte (481 passed).
