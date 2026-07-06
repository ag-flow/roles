# BUG-20 — `finalize_upload` non atomique : double appel → double transcription puis re-dépôt

- **Zone** : acquisition / upload
- **Fichier(s)** : `backend/src/role_builder/services/acquisition/upload/finalize.py:60-98` ; worker : `docker/transcription-worker/.../db.py:121-127` (`update_source_item_to_transcribed`)
- **Sévérité** : majeure
- **Confiance** : moyenne
- **Difficulté de correction** : **Opus**

## Problème

L'idempotence repose sur un read-then-act (`get_by_id` puis check `status == "awaiting_upload"`) sans verrou ni UPDATE conditionnel. Deux `finalize_upload` concurrents (retry client après timeout, ffmpeg long) passent tous deux le check et insèrent chacun un `transcription_job`. Cascade : le worker traite les deux jobs ; `update_source_item_to_transcribed` est inconditionnel, donc le second job repasse l'item de `deposited` à `transcribed` → le DepositWorker le re-claim → document docflow déposé en double (et coût SaaS doublé).

## Scénario d'échec

Finalize d'une vidéo de 40 min, la passerelle MCP timeout pendant l'extraction ffmpeg, le pilote rejoue `finalize_upload` → deux jobs, deux transcriptions payées, deux documents docflow pour le même item.

## Piste de résolution

Claim atomique du slot en tête de finalize : `UPDATE source_items SET status='audio_ready' ... WHERE id=$1 AND status='awaiting_upload' RETURNING *` ; si 0 ligne, retourner le statut courant. Côté worker, rendre `update_source_item_to_transcribed` conditionnel (`WHERE status IN ('queued_transcription','transcribing')`).

## Pourquoi Opus

Deux UPDATE conditionnels, mais il faut repenser l'ordre extraction-ffmpeg/transition pour ne pas laisser un `audio_ready` orphelin si ffmpeg échoue (couplé à BUG-21).

## ✅ Résolu (2026-07-06)

Réglé par la refonte BUG-22 : `claim_finalize_slot` (UPDATE conditionnel WHERE status='awaiting_upload') rend le finalize atomique — un second appel concurrent reçoit None/le statut courant, plus de double transcription ni re-dépôt.

Vérifié : suite backend verte (481 passed).
