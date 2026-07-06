# BUG-21 — Le cleanup périodique peut détruire un slot pendant son `finalize` (ffmpeg)

- **Zone** : acquisition / upload
- **Fichier(s)** : `backend/src/role_builder/services/acquisition/upload/cleanup.py:31-48` et `finalize.py:66-95` ; déclenché par `scheduler.py:59-61`
- **Sévérité** : majeure
- **Confiance** : moyenne
- **Difficulté de correction** : **Opus**

## Problème

Pendant toute la durée de l'extraction ffmpeg (jusqu'à 30 min de timeout), l'item reste `status='awaiting_upload'` — le statut n'est mis à jour qu'après `_resolve_audio_key`. Si le TTL expire entre-temps, `cleanup_expired_slots` voit l'item expiré, supprime l'objet MinIO source et la ligne `source_items`. Le finalize en vol échoue alors : `update_source_item_status` ne matche plus rien et `transcription_jobs.insert_job` viole la FK `source_item_id` → exception brute (pas une `AcquisitionError`), upload perdu, mp3 extrait orphelin dans le bucket.

## Scénario d'échec

PUT d'une grosse vidéo à T+55 min du slot (TTL 1 h), `finalize_upload` à T+58, ffmpeg dure 6 min, le job cleanup passe à T+62 → suppression sous les pieds du finalize.

## Piste de résolution

Faire franchir l'item dans un état intermédiaire non nettoyable (ex. `audio_ready`/`finalizing`) via UPDATE conditionnel dès l'entrée du finalize (résout aussi BUG-20), avant l'extraction. Prévoir un chemin de retour propre vers `failed` si ffmpeg échoue.

## Pourquoi Opus

Couplé au claim atomique du finalize ; nécessite un nouvel état et un chemin d'échec propre.

## ✅ Résolu (2026-07-06)

Réglé par la refonte BUG-22 : le finalize claime immédiatement le slot hors de 'awaiting_upload' (→ pending_extraction/audio_ready) ; le cleanup ne cible que 'awaiting_upload', il ne peut plus détruire un slot en cours de traitement.

Vérifié : suite backend verte (481 passed).
