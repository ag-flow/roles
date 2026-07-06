# BUG-06 — docker_runner : stderr=PIPE jamais lu → deadlock du container, orchestrator gelé

- **Zone** : services cœur / docker runner
- **Fichier(s)** : `backend/src/role_builder/services/docker_runner.py:48` (et boucle `57-70`)
- **Sévérité** : majeure
- **Confiance** : haute
- **Difficulté de correction** : **Sonnet**

## Problème

Le subprocess est créé avec `stderr=asyncio.subprocess.PIPE` mais stderr n'est jamais consommé. Dès que le container écrit ~64-128 Ko sur stderr (buffer StreamReader + buffer pipe OS), le process docker se bloque en écriture ; `proc.stdout.readline()` n'atteint jamais EOF.

## Scénario d'échec

Un scraper verbeux sur stderr (traceback Python répété, warnings, yt-dlp mal redirigé) → `run_container` suspendu pour toujours → comme `run_loop` traite les jobs séquentiellement, **tout l'orchestrator est gelé** jusqu'au redémarrage du backend ; le job reste `processing`.

## Piste de résolution

Soit `stderr=asyncio.subprocess.DEVNULL`, soit une tâche concurrente qui draine/loggue stderr (préférable pour le debug). `stderr=STDOUT` est exclu (pollue le NDJSON).

## Pourquoi Sonnet

Une `asyncio.create_task` de drainage + `await` à la fin.

## ✅ Résolu (2026-07-06)

_drain_stderr : task de drainage continu de stderr, plus de blocage du pipe.

Vérifié : suite backend verte (481 passed).
