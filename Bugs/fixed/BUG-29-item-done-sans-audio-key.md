# BUG-29 — `item_done` sans `audio_s3_key` → item en `queued_transcription` sans job

- **Zone** : services cœur / event handlers (confirmé par 2 agents)
- **Fichier(s)** : `backend/src/role_builder/services/event_handlers.py:169-192`
- **Sévérité** : mineure
- **Confiance** : haute
- **Difficulté de correction** : **Sonnet**

## Problème

`_handle_item_done` n'insère un `transcription_job` que si `audio_s3_key` est truthy (ligne 169), mais met **inconditionnellement** l'item à `status='queued_transcription'` (lignes 186-192). Si l'event arrive sans `audio_s3_key` (scraper bogué ou event partiel), l'item prétend être en file de transcription alors qu'aucun worker ne le prendra jamais — état incohérent, invisible dans les compteurs d'échec.

## Scénario d'échec

Event `{"type":"item_done","item_id":"v1"}` (clé absente) → item `queued_transcription` définitif, jamais transcrit, jamais `failed`, la requête d'acquisition ne se termine jamais côté `request_status`.

## Piste de résolution

Si `audio_s3_key` manquant, marquer l'item `failed` avec un code d'erreur explicite (ou logger + laisser `audio_ready`), et ne passer `queued_transcription` que dans la branche avec job.

## Pourquoi Sonnet

Déplacer la transition dans la branche conditionnelle + un test.

## ✅ Résolu (2026-07-06)

Réglé avec BUG-19 : dans _handle_item_done, un event item_done sans audio_s3_key marque l'item 'failed' (ITEM_DONE_WITHOUT_AUDIO) au lieu de le laisser 'queued_transcription' sans job.

Vérifié : suite backend verte (481 passed).
