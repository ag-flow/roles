# BUG-17 — Annulation non étanche : dépôts et relances possibles sur une requête `cancelled`

- **Zone** : acquisition / admin + sélection + dépôt (confirmé par 2 agents)
- **Fichier(s)** : `backend/src/role_builder/services/acquisition/admin.py:18-47` ; `selection.py:31-56` ; `upload/finalize.py:53-66` ; `db_helpers/deposit_queue.py:21-40`
- **Sévérité** : majeure
- **Confiance** : haute
- **Difficulté de correction** : **Opus**

## Problème

Trois trous après un `cancel_request` :
1. `claim_next_for_deposit` claim tout item `status='transcribed'` sans regarder la requête : les items déjà transcrits continuent d'être déposés dans docflow après le cancel.
2. `select_items` et `retry_failed` ne vérifient pas `status == "cancelled"` : ils ré-enqueuent des downloads sur une requête annulée. Le code d'erreur `NOT_IN_DISCOVERED_STATE`/`ALREADY_CANCELLED` prévu par la spec (§5.6) n'est implémenté nulle part (grep : zéro occurrence).
3. `finalize_upload` accepte un slot d'une requête upload annulée et l'envoie en transcription.

## Scénario d'échec

`cancel_request("yt-x")` alors que 3 items sont `transcribed` → `cancelled_jobs` retourné, mais les 3 transcripts sont quand même déposés dans docflow dans les secondes qui suivent ; ou bien `select_items` post-cancel relance des téléchargements facturés.

## Piste de résolution

- (1) Au cancel, basculer les items `transcribed`/`queued_transcription` de la source vers un état neutre (ex. `cancelled` ou `selected=false`) ou filtrer le claim de dépôt par statut de requête.
- (2)(3) Gardes `ALREADY_CANCELLED`/`REQUEST_CLOSED` en tête de `select_items`, `retry_failed`, `finalize_upload`.

## Pourquoi Opus

Le volet dépôt touche le modèle de queue « source_items comme queue » (choix d'état neutre, cohérence avec le DepositWorker) ; les gardes sont simples mais l'ensemble demande une décision de cohérence.

## ✅ Résolu (2026-07-06)

Gardes ALREADY_CANCELLED en tête de select_items/retry_failed/finalize_upload ; claim_next_for_deposit exclut les items d'une requête cancelled (NOT EXISTS).

Vérifié : suite backend verte (481 passed).
