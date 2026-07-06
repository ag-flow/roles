# BUG-39 — CORS `allow_origins=["*"]` combiné à `allow_credentials=True`

- **Zone** : config / CORS
- **Fichier(s)** : `backend/src/role_builder/main.py:198-204`
- **Sévérité** : mineure
- **Confiance** : haute
- **Difficulté de correction** : **Sonnet**

## Problème

Configuration contradictoire : la spec Fetch interdit `Access-Control-Allow-Origin: *` avec credentials ; Starlette ne reflète l'origine que si la requête porte un cookie. Concrètement, toute origine web peut appeler l'API (le Bearer n'étant pas un credential CORS), et le jour où une auth cookie/session serait introduite, le wildcard+credentials deviendrait soit inopérant (bloqué navigateur), soit un reflet d'origine universel. Le commentaire « à restreindre en prod » existe mais rien ne l'applique (pas de setting).

## Scénario d'échec

Un site tiers exécute depuis le navigateur d'un utilisateur des appels non authentifiés (`/api/version`, probing 401/404 des routes) et, si un token fuit dans le front, l'exploite depuis n'importe quelle origine sans être bloqué par CORS.

## Piste de résolution

Setting `cors_allow_origins` (liste), défaut restrictif en prod ; retirer `allow_credentials` tant que l'auth est Bearer-only.

## Pourquoi Sonnet

Un champ Settings + injection dans le middleware.

## ✅ Résolu (2026-07-06)

allow_credentials=False (auth Bearer) + origines configurables via settings.cors_allow_origins ; plus de wildcard+credentials.

Vérifié : suite backend verte (481 passed).
