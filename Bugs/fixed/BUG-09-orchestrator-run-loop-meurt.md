# BUG-09 — ScraperOrchestrator : une erreur DB transitoire tue la boucle pour toute la vie du process

- **Zone** : services cœur / orchestrateur
- **Fichier(s)** : `backend/src/role_builder/services/scraper_orchestrator.py:95-111` (et `54`, `85`)
- **Sévérité** : majeure
- **Confiance** : haute
- **Difficulté de correction** : **Sonnet**

## Problème

Contrairement à `WorkerManager.run_auto_stop_loop` et `DepositWorker.run_loop` qui enveloppent leur itération dans un `try/except`, `run_loop` appelle `sj.claim_next_pending_job` sans protection ; de plus `mark_job_processing` (ligne 54) est hors du `try` de `process_one_job`, et le `mark_job_failed` du bloc `except` (ligne 85) peut lui-même lever. Toute exception (restart PG, pool épuisé, timeout réseau) sort de `run_loop`, la task `scraper-orchestrator` meurt, et l'exception n'est loggée qu'au shutdown (le lifespan attend la task dans son `finally`).

## Scénario d'échec

Redémarrage PostgreSQL de quelques secondes → `claim_next_pending_job` lève `ConnectionDoesNotExistError` → plus aucun job de scraping traité jusqu'au redémarrage du backend, sans aucun log au moment de l'incident.

## Piste de résolution

`try/except Exception` + `log.exception` autour du corps de l'itération (comme les deux autres boucles), avec un backoff court en cas d'erreur.

## Pourquoi Sonnet

Même pattern que les boucles voisines, à recopier.

## ✅ Résolu (2026-07-06)

claim protégé par try/except (via refonte BUG-10) et _process_and_release logge toute exception : la boucle survit à une erreur DB transitoire.

Vérifié : suite backend verte (481 passed).
