# BUG-07 — docker_runner : aucun cleanup du subprocess si le générateur est abandonné

- **Zone** : services cœur / docker runner
- **Fichier(s)** : `backend/src/role_builder/services/docker_runner.py:44-72`, croisé avec `scraper_orchestrator.py:78-86`
- **Sévérité** : majeure
- **Confiance** : haute
- **Difficulté de correction** : **Sonnet**

## Problème

`run_container` n'a pas de `try/finally` : si le consommateur sort du `async for` par exception (ex. `handle_scraper_event` lève — un `event["item_id"]` manquant suffit, `event_handlers.py:98`), le générateur est fermé sans `kill()`/`wait()` du process. Le docker CLI continue de tourner ; quand le StreamReader ne consomme plus, le flow control suspend la lecture → le CLI finit bloqué en écriture stdout, process fuité indéfiniment, et le container continue de scraper/uploader alors que le job est marqué `failed`.

## Scénario d'échec

N'importe quelle exception de traitement d'event en cours de stream → job `failed` en DB, mais container et process `docker run` toujours vivants ; accumulation de processus bloqués au fil des échecs.

## Piste de résolution

Entourer la boucle de streaming d'un `try/finally` qui, si le process tourne encore, fait `proc.kill()` puis `await proc.wait()` (le `GeneratorExit` arrive au point de `yield`).

## Pourquoi Sonnet

Ajout d'un `try/finally` localisé.

## ✅ Résolu (2026-07-06)

try/finally autour du streaming : proc.kill()+wait() si le générateur est abandonné ; task stderr annulée.

Vérifié : suite backend verte (481 passed).
