# BUG-32 — POST /sources/{id}/items/select : non transactionnel, non idempotent, 500 FK

- **Zone** : routes HTTP / sélection
- **Fichier(s)** : `backend/src/role_builder/routes/sources.py:118-156` ; `db_helpers/source_items.py:219-243`
- **Sévérité** : majeure
- **Confiance** : haute
- **Difficulté de correction** : **Opus**

## Problème

Complément REST de BUG-13, avec des défauts propres à la route :
1. `insert_job` est appelé pour chaque `item_id` sans vérifier existence/appartenance à `source_id` (voir BUG-13).
2. Un UUID inexistant lève une FK violation → **500 au milieu de la boucle**, après l'UPDATE `selected` et la création partielle de jobs (pas de transaction).
3. `select_items` retourne `len(item_ids)`, pas le rowcount réel.
4. Contrairement à la façade MCP (`get_active_job_for_item`), la route REST n'est **pas idempotente** : chaque re-POST duplique les jobs de download.

## Scénario d'échec

`POST /api/sources/S1/items/select` avec `item_ids=[item-de-S2, uuid-bidon]` → réponse 500, `selected` déjà modifié, un job download créé pour l'item de S2 sous S1 ; le pipeline télécharge une vidéo hors périmètre.

## Piste de résolution

Charger les items par `id = ANY($2) AND source_id = $1`, rejeter (400/404) les ids hors source, envelopper UPDATE + inserts dans une **transaction**, retourner le rowcount réel, réutiliser `get_active_job_for_item` pour l'idempotence.

## Pourquoi Opus

Requête de validation + transaction commune route/helper + idempotence : refactor du helper partagé.

## ✅ Résolu (2026-07-06)

Route select : validation d'appartenance via list_items_by_ids (item hors source → 400, pas de FK 500), idempotence via get_active_job_for_item.

Vérifié : suite backend verte (481 passed).
