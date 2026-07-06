# BUG-60 — `SCRAPER_IMAGE_TAG`/`WORKER_IMAGE_TAG` du `.env` silencieusement ignorés

- **Zone** : infra / config
- **Fichier(s)** : `docker-compose-dev.yml:55` (`SCRAPER_IMAGE_TAG: ${IMAGE_TAG:-latest}`) et `:66` (`WORKER_IMAGE_TAG: ${IMAGE_TAG:-latest}`) ; `.env.example:6-8`
- **Sévérité** : mineure
- **Confiance** : haute
- **Difficulté de correction** : **Sonnet**

## Problème

Le compose mappe les variables d'environnement du conteneur `SCRAPER_IMAGE_TAG`/`WORKER_IMAGE_TAG` sur `${IMAGE_TAG}` au lieu de `${SCRAPER_IMAGE_TAG:-${IMAGE_TAG:-latest}}`. Les valeurs saisies dans `.env` (documentées « par défaut = IMAGE_TAG ») ne sont jamais transmises au backend (`settings.scraper_image_tag`).

## Scénario d'échec

L'opérateur épingle `SCRAPER_IMAGE_TAG=fix-yt-dlp` dans `.env` pour tester une image scraper corrigée → le backend continue de lancer `agflow-scraper-youtube:latest` ; le comportement observé ne correspond pas à la configuration, diagnostic long.

## Piste de résolution

`SCRAPER_IMAGE_TAG: ${SCRAPER_IMAGE_TAG:-${IMAGE_TAG:-latest}}` (idem WORKER).

## Pourquoi Sonnet

Deux valeurs par défaut à corriger dans le compose.

## ✅ Résolu (2026-07-06)

docker-compose-dev.yml : SCRAPER_IMAGE_TAG/WORKER_IMAGE_TAG utilisent ${SCRAPER_IMAGE_TAG:-${IMAGE_TAG:-latest}} — les valeurs .env sont enfin transmises au backend.

(Correction shell/compose, non couverte par la suite pytest.)
