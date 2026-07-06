# BUG-22 — `finalize_upload` bloque l'appel MCP pendant toute l'extraction ffmpeg et charge la vidéo en RAM

- **Zone** : acquisition / upload / façade MCP
- **Fichier(s)** : `backend/src/role_builder/services/acquisition/upload/finalize.py:96-118` ; `upload/audio_extraction.py:37-49`
- **Sévérité** : majeure
- **Confiance** : haute
- **Difficulté de correction** : **Fable**

## Problème

Violation du principe §1.1 de la spec (« Aucun tool ne bloque ») : le tool `roles__finalize_upload` exécute inline download MinIO complet → ffmpeg (garde-fou 1800 s) → upload. En plus : `download_bytes` charge tout l'objet en mémoire (politique MinIO §5.5 : jusqu'à 2 GB) et `source_path.write_bytes(video_bytes)` / `target_path.read_bytes()` sont des I/O synchrones exécutées **sur l'event loop** (pas dans `to_thread`), gelant tout le backend (autres tools MCP, API, orchestrator) pendant plusieurs secondes par gigaoctet.

## Scénario d'échec

Upload d'une conférence vidéo de 1,5 GB → `finalize_upload` ne répond pas pendant plusieurs minutes → timeout HTTP côté passerelle/pilote (réponse perdue, statut inconnu, favorisant le double appel de BUG-20), et pics mémoire ~2× la taille du fichier ; pendant les `write_bytes`, l'event loop entier est gelé.

## Piste de résolution

Rendre le finalize asynchrone (passer l'item en `audio_extracting`, extraction dans un job/tâche de fond, le pilote suit via `request_status`). A minima : streamer via fichiers temporaires (`fget_object`/`fput_object`) et déplacer les I/O fichier dans `to_thread`.

## Pourquoi Fable

Le vrai correctif est architectural : introduire un nouvel état et déporter l'extraction dans un worker asynchrone, en cohérence avec le modèle « ticket » et les autres queues. (Le simple correctif event-loop/mémoire — `to_thread` + streaming — serait Opus, mais ne résout pas la violation du contrat « aucun tool ne bloque ».)

## ✅ Résolu (2026-07-05)

Refonte en extraction asynchrone, modèle DepositWorker. Nouveau cycle d'item :
`awaiting_upload → pending_extraction → extracting_audio → audio_ready/queued_transcription` (ou `failed`).

- **`finalize_upload` ne bloque plus** : pour un média vidéo, il claime atomiquement le slot en `pending_extraction` (`db_helpers/source_items_upload.claim_finalize_slot`) et retourne immédiatement `{status: "pending_extraction"}`. Le ffmpeg n'est plus dans l'appel MCP → contrat §1.1 « aucun tool ne bloque » respecté. Média audio : entrée directe en transcription (inchangé, appel court).
- **Nouveau `AudioExtractionWorker`** (`services/acquisition/upload/extraction_worker.py`) : boucle de fond `recover()`/`tick()`/`run_loop()`/`process_item()`, claim FIFO `pending_extraction → extracting_audio` (FOR UPDATE SKIP LOCKED), ffmpeg avec retry/backoff, puis entrée en transcription ; épuisement → `failed` (`AUDIO_EXTRACTION_FAILED`). Câblé dans le lifespan (`main.py`), flag `disable_extraction_worker`.
- **Effet de bord positif** : le claim atomique résout aussi **BUG-20** (double finalize → le second reçoit `None`/statut courant) et **BUG-21** (un slot en `pending_extraction`/`extracting_audio` n'est plus `awaiting_upload`, donc hors de portée du cleanup). Entrée en transcription idempotente (garde `has_job_for_item`) → pas de double job en reprise crash.
- **Event loop** : `audio_extraction.py` — les `write_bytes`/`read_bytes` fichier passent désormais par `asyncio.to_thread`.
- **Reste (mineur, non bloquant)** : `download_bytes` charge encore l'objet en RAM dans le thread du worker (borné par la taille du fichier, mais hors du chemin MCP et hors event loop) ; un vrai streaming `fget_object`/`fput_object` via fichiers temporaires reste un raffinement possible (nécessite d'étendre `MinioWrapper`).

Tests : `tests/services/acquisition/test_upload_extraction_worker.py` (5 tests) + `test_upload_finalize.py` (comportement vidéo async) + `test_acceptance_upload.py`. Suite complète : 475 passed (2 échecs préexistants sur `test_migration_0009`, sans rapport).
