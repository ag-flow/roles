# BUG-19 — Échecs de découverte/transcription jamais propagés : requêtes et items bloqués sans issue

- **Zone** : acquisition / orchestrateur / worker (confirmé par 3 agents)
- **Fichier(s)** : `backend/src/role_builder/services/scraper_orchestrator.py:87-93` ; `services/event_handlers.py:196-215` ; `docker/transcription-worker/worker/main.py:120-172` ; symptôme dans `services/acquisition/status.py` et `status_shape.py:53-61`
- **Sévérité** : majeure
- **Confiance** : haute
- **Difficulté de correction** : **Opus**

## Problème

La spec §2.3 déclare un statut `failed` au niveau requête, mais aucun chemin du code ne le produit (`update_status` n'est appelé qu'avec `discovered`/`acquiring`/`cancelled`). Trois transitions d'échec manquent :
1. Un job `discover` qui échoue (container KO, cookies invalides, chaîne inexistante) marque le job `failed` mais ne touche ni la source (reste `pending_discovery`) ni la requête (reste `discovering`) : `list_discovered.discovery_complete=false` et `request_status=discovering` pour toujours, aucun code d'erreur exposé.
2. Un job de transcription épuisé en échec ne repasse jamais le `source_item` en `failed` (le worker ne fait que `mark_job_failed`) : item bloqué `queued_transcription`, invisible pour `retry_failed`, requête jamais `completed`.
3. `_handle_item_done` sans `audio_s3_key` passe quand même l'item à `queued_transcription` sans créer de job — même blocage (voir BUG-29).

## Scénario d'échec

Clé OpenAI révoquée → tous les jobs de transcription échouent → tous les items restent `queued_transcription`, `request_status` affiche `acquiring` indéfiniment, `retry_failed` retourne `{retried_count: 0}`. Le modèle « ticket asynchrone » est cassé : impossible de savoir qu'il faut abandonner.

## Piste de résolution

- (1) Sur `mark_job_failed` d'un `discover`, poser un statut d'échec sur la source et la requête (`discovery_failed`/`failed`) via `ar.get_by_source_id`, exposé par `derive_display_status`.
- (2) Faire marquer l'item `failed` par le worker (ou un réconciliateur backend sur jobs `failed`).
- (3) Traiter `item_done` sans clé audio comme `item_failed`.

## Pourquoi Opus

Trois points de code + un nouveau statut à ajouter au contrat §2.3, sans casser le flux V1 sans requête associée.

## ✅ Résolu (2026-07-06)

(1) discover échoué → source discovery_failed + requête failed (orchestrator._propagate_discover_failure) ; (2) réconciliateur périodique fail_items_with_dead_transcription_jobs (scheduler, 2 min) ; (3) item_done sans audio → failed. derive_display_status reconnaît 'failed'.

Vérifié : suite backend verte (481 passed).
