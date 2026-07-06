# BUG-02 — Backend conteneurisé sans CLI docker ni socket : aucun scraper/worker ne démarre

- **Zone** : infra / déploiement
- **Fichier(s)** : `docker-compose-dev.yml` (service `backend`, aucun volume `/var/run/docker.sock`) ; `backend/Dockerfile:10-12` (installe seulement curl/ca-certificates/ffmpeg) ; recoupé avec `backend/src/role_builder/services/docker_runner.py:40` (`["docker","run","--rm","-i",…]`) et `worker_manager.py:116` (`docker run -d`)
- **Sévérité** : critique
- **Confiance** : haute
- **Difficulté de correction** : **Opus**

## Problème

Tout le pipeline d'acquisition repose sur des `subprocess docker run` (scrapers one-shot, workers transcription), mais l'image backend ne contient pas le binaire `docker` et le compose ne monte pas le socket Docker. `DISABLE_ORCHESTRATOR`/`DISABLE_WORKER_MANAGER` valent `false` par défaut.

## Scénario d'échec

Déploiement standard `sudo ./dev-deploy.sh` → le smoke test `/health` passe (le backend démarre), puis la première acquisition soumise : le claim d'un scraping job appelle `run_container` → `FileNotFoundError: 'docker'` → job en échec, tous les items en `failed`. Aucune vidéo ne sera jamais scrapée ni transcrite dans ce déploiement.

Second étage du même problème : même avec le socket monté, les containers scrapers lancés sans `--network` du projet compose ne résoudront pas `minio:9000`.

## Piste de résolution

Monter `/var/run/docker.sock` dans le service backend + installer `docker-ce-cli` dans l'image (ou passer à l'API Docker via `aiodocker`) ; passer `--network <projet>_default` aux `docker run` pour que MinIO/Postgres soient résolvables par les containers éphémères.

## Pourquoi Opus

Le compose et le Dockerfile sont simples à modifier, mais le raccordement réseau des containers éphémères doit être vérifié de bout en bout (résolution DNS `minio:9000`, sécurité du montage du socket).
