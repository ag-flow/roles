# BUG-48 — Secrets passés en argv de `docker run` (visibles via /proc et `docker inspect`)

- **Zone** : services cœur / worker manager + docker runner
- **Fichier(s)** : `backend/src/role_builder/services/worker_manager.py:110-123` ; `docker_runner.py:35-40` (appelé par `scraper_orchestrator._build_env:116-125`)
- **Sévérité** : mineure
- **Confiance** : haute
- **Difficulté de correction** : **Opus**

## Problème

`WorkerManager.spawn_worker` passe la clé API provider du user, `DATABASE_URL` (avec mot de passe) et `MINIO_SECRET_KEY` en `-e K=V` sur la ligne de commande du CLI docker ; idem `docker_runner` pour les cookies utilisateur (`*_COOKIES_B64`) et les credentials MinIO. La ligne de commande est lisible par tout process du host (`ps`, `/proc/<pid>/cmdline`) pendant l'exécution du CLI, et les valeurs persistent dans `docker inspect` du container.

## Scénario d'échec

N'importe quel process non privilégié co-hébergé fait `ps aux` pendant un spawn → exfiltration de la clé OpenAI/Deepgram du user, des cookies de session YouTube/Instagram et des credentials DB/MinIO.

## Piste de résolution

Écrire les variables dans un fichier temporaire 0600 et utiliser `docker run --env-file`, en le supprimant après. `docker inspect` restera un point d'exposition (inhérent aux env Docker) — pour les scrapers, les credentials MinIO passent déjà par stdin dans le payload, la duplication en env peut être réduite.

## Pourquoi Opus

Gestion du fichier temporaire + nettoyage sur toutes les branches d'erreur (y compris échec du spawn), pour worker_manager et docker_runner.

## ✅ Résolu (2026-07-06)

docker_runner.env_file() écrit un env-file 0600 supprimé après ; docker_runner et worker_manager utilisent --env-file au lieu de -e K=V. Secrets hors argv/proc.

Vérifié : suite backend verte (481 passed).
