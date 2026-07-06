# BUG-59 — `IMAGE_TAG` du `.env` lu par compose mais pas par `build.sh`

- **Zone** : infra / build
- **Fichier(s)** : `dev-deploy.sh:119-121` (appel `./build.sh` sans sourcer `.env`) ; `build.sh:4` (`IMAGE_TAG="${IMAGE_TAG:-latest}"`) ; `docker-compose-dev.yml:36,85` (`image: …:${IMAGE_TAG:-latest}`)
- **Sévérité** : mineure
- **Confiance** : haute
- **Difficulté de correction** : **Sonnet**

## Problème

`docker compose` interpole `${IMAGE_TAG}` depuis le fichier `.env` du projet, mais `build.sh` ne lit que l'environnement du shell ; `dev-deploy.sh` ne sourçant jamais `.env`, les deux peuvent diverger.

## Scénario d'échec

`IMAGE_TAG=v2` dans `.env` → `build.sh` tague `backend-roles:latest`, compose exige `backend-roles:v2` → `up -d --pull never` échoue « image not found ».

## Piste de résolution

Dans `dev-deploy.sh`, exporter `IMAGE_TAG="$(_env_get IMAGE_TAG)"` avant d'appeler `build.sh`.

## Pourquoi Sonnet

Une ligne d'export.

## ✅ Résolu (2026-07-06)

dev-deploy.sh exporte IMAGE_TAG (lu depuis .env) avant d'appeler build.sh : les images sont taguées comme le compose les attend au up --pull never.

(Correction shell/compose, non couverte par la suite pytest.)
