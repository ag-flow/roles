# BUG-10 — ScraperOrchestrator : le sémaphore `max_concurrent_scrapers` n'a aucun effet

- **Zone** : services cœur / orchestrateur
- **Fichier(s)** : `backend/src/role_builder/services/scraper_orchestrator.py:47`, `109-110`
- **Sévérité** : majeure
- **Confiance** : haute
- **Difficulté de correction** : **Opus**

## Problème

`run_loop` fait `async with self._semaphore: await self.process_one_job(job)` dans la boucle — le job est attendu jusqu'au bout avant de claim le suivant. Le sémaphore n'est jamais contendu ; un seul container scraper tourne à la fois quel que soit `settings.max_concurrent_scrapers`, en contradiction avec le docstring du module (« Cap simultané : `settings.max_concurrent_scrapers` via `asyncio.Semaphore` ») et la config.

## Scénario d'échec

`MAX_CONCURRENT_SCRAPERS=3`, 3 jobs pending → traités un par un ; un job long (chaîne de 200 vidéos) bloque tous les autres tenants/requêtes (aggravé par BUG-06 : un job gelé = orchestrator gelé).

## Piste de résolution

`asyncio.create_task` par job avec acquisition du sémaphore dans la task (acquérir **avant** de claim pour ne pas claim plus que la capacité), et suivi des tasks en vol pour le shutdown.

## Pourquoi Opus

Gestion du cycle de vie des tasks : acquisition avant claim, arrêt propre au shutdown, remontée des exceptions par task.

## ✅ Résolu (2026-07-06)

run_loop refondu : acquisition du sémaphore *avant* le claim + une task par job (`_process_and_release`). Jobs réellement concurrents jusqu'à max_concurrent_scrapers ; drain des tasks en vol au shutdown.

Vérifié : suite backend verte (481 passed).
