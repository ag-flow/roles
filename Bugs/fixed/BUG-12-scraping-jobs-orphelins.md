# BUG-12 — scraping_jobs `claimed`/`processing` orphelins après crash : aucune récupération

- **Zone** : services cœur / orchestrateur
- **Fichier(s)** : `backend/src/role_builder/services/scraper_orchestrator.py:95-111` (absence d'équivalent à `DepositWorker.recover`), croisé avec `db_helpers/scraping_jobs.py` (`claim_next_pending_job` passe le job à `claimed`)
- **Sévérité** : majeure (rapportée mineure par l'agent, mais bloque définitivement l'acquisition)
- **Confiance** : haute
- **Difficulté de correction** : **Sonnet**

## Problème

Le claim persiste `status='claimed'` (puis `'processing'`) hors de tout lease/timeout. Si le backend crash ou est redéployé pendant un job (fréquent : un download de chaîne dure longtemps), le job reste `claimed`/`processing` pour toujours — `claim_next_pending_job` ne sélectionne que `pending`. Le `DepositWorker` a exactement ce mécanisme (`requeue_stale_depositing` appelé dans `run_loop`), l'orchestrator non ; l'asymétrie montre que ce n'est pas un choix.

## Scénario d'échec

Redéploiement pendant un job de download → item(s) `pending_download` sélectionnés avec un job `processing` fantôme ; `get_active_job_for_item` (utilisé par `select_items` pour l'idempotence) considère le job « en vol » → même une re-sélection ne ré-enqueue pas ; acquisition définitivement bloquée.

## Piste de résolution

Au démarrage de `run_loop`, requeue `claimed`/`processing` → `pending` (hypothèse mono-orchestrator déjà documentée), ou lease avec `claimed_at` + timeout.

## Pourquoi Sonnet

Même pattern que `requeue_stale_depositing`, à transposer.

## ✅ Résolu (2026-07-06)

requeue_stale_jobs (claimed/processing → pending) appelé au démarrage de run_loop (reprise crash, hypothèse mono-orchestrator).

Vérifié : suite backend verte (481 passed).
