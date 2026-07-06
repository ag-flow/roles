# BUG-58 — `dev-deploy.sh` régénère les credentials sans invalider les volumes initialisés

- **Zone** : infra / déploiement
- **Fichier(s)** : `dev-deploy.sh:86-104` ; `docker-compose-dev.yml` (volumes nommés `postgres_data`, `minio_data`, `down` sans `-v`)
- **Sévérité** : majeure
- **Confiance** : haute
- **Difficulté de correction** : **Opus**

## Problème

Quand `.env` porte une valeur vide ou `changeme_in_real_env`, le script génère de nouveaux `POSTGRES_USER/PASSWORD` (et MinIO). Or l'image postgres n'applique ces variables **qu'à l'initialisation d'un volume vide** ; le `docker compose down` du script ne supprime pas les volumes.

## Scénario d'échec

Un opérateur fait `cp .env.example .env && docker compose -f docker-compose-dev.yml up -d` (volume initialisé avec `rb/changeme_in_real_env`), puis passe au geste officiel `sudo ./dev-deploy.sh` → creds régénérés dans `.env`, volume inchangé → le backend boucle sur `password authentication failed`, le smoke test échoue après 90 s sans indiquer la cause. Même piège si `.env` est recréé après une perte alors que les volumes subsistent.

## Piste de résolution

Après régénération, détecter un volume `postgres_data` préexistant et soit exécuter un `ALTER USER`/re-création via les anciens creds, soit refuser explicitement avec un message « volume initialisé avec d'autres credentials — supprimer le volume ou restaurer l'ancien .env ».

## Pourquoi Opus

Détection de l'état du volume + chemin de réconciliation (ALTER USER ou refus explicite).
