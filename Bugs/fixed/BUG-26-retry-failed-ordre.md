# BUG-26 — `retry_failed` réinitialise l'item avant le check d'idempotence

- **Zone** : acquisition / admin
- **Fichier(s)** : `backend/src/role_builder/services/acquisition/admin.py:78-90`
- **Sévérité** : mineure
- **Confiance** : moyenne
- **Difficulté de correction** : **Sonnet**

## Problème

L'ordre est `reset_for_retry` (item → `pending_download`) puis `get_active_job_for_item` → `continue`. Si un item est `failed` alors qu'un job download pour cet item est encore `claimed`/`processing` (échec signalé par event pendant que le job tourne), l'item a déjà été remis `pending_download` mais aucun nouveau job n'est créé, et le job actif détecté peut ne jamais retraiter cet item → item ni `failed` ni réellement en vol, et `retried_count` ne le compte pas alors qu'il a été modifié.

## Scénario d'échec

Deux appels `retry_failed` rapprochés, ou un item échoué par event pendant qu'un job single-item est encore en cours : reset sans nouveau job → item silencieusement coincé en `pending_download`.

## Piste de résolution

Tester `get_active_job_for_item` **avant** `reset_for_retry`, et ne compter `retried` que si un job est effectivement inséré (ou un reset dépôt effectué).

## Pourquoi Sonnet

Réordonnancement de deux appels + condition de comptage.

## ✅ Résolu (2026-07-06)

get_active_job_for_item testé AVANT reset_for_retry : plus d'item remis pending_download sans nouveau job.

Vérifié : suite backend verte (481 passed).
