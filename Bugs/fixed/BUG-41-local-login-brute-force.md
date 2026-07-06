# BUG-41 — POST /api/auth/local-login : brute force illimité sur le compte admin

- **Zone** : auth / local admin
- **Fichier(s)** : `backend/src/role_builder/routes/auth_local.py:35-61`
- **Sévérité** : mineure
- **Confiance** : haute
- **Difficulté de correction** : **Sonnet**

## Problème

Aucune limitation de débit ni délai sur les échecs : le mot de passe admin (12 octets hex générés par `dev-deploy.sh`, mais librement définissable en `.env`) peut être brute-forcé à pleine vitesse HTTP ; la comparaison est constant-time mais rien ne freine le volume. Le endpoint donne accès à un JWT valable 12 h sur toute l'API.

## Scénario d'échec

Instance exposée (port 8000 publié) avec `LOCAL_ADMIN_ENABLED=true` et mot de passe faible saisi à la main → dictionnaire à ~1000 req/s jusqu'au 200.

## Piste de résolution

Compteur d'échecs avec backoff exponentiel en mémoire (ou table), et `asyncio.sleep` fixe sur échec.

## Pourquoi Sonnet

Throttle en mémoire suffisant pour un mono-process.

## ✅ Résolu (2026-07-06)

Throttle en mémoire : délai exponentiel (0.5→8s) au-delà de 3 échecs par username, reset sur succès.

Vérifié : suite backend verte (481 passed).
