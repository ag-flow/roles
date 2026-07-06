# BUG-30 — Hosts YouTube/TikTok courants non reconnus (`m.`, `music.`, `vm.tiktok.com`)

- **Zone** : acquisition / détection de plateforme
- **Fichier(s)** : `backend/src/role_builder/services/acquisition/platform_detection.py:11-19`
- **Sévérité** : mineure
- **Confiance** : haute
- **Difficulté de correction** : **Sonnet**

## Problème

`_HOST_MAP` ne contient que les hosts canoniques + `www`. Les URL mobiles (`m.youtube.com/watch?...`), les liens courts TikTok (`vm.tiktok.com/xxx`, format de partage par défaut de l'app) et `music.youtube.com` lèvent `UNSUPPORTED_PLATFORM` alors que la plateforme est supportée. Par ailleurs une URL sans schéma (`youtube.com/watch?v=x`) donne `netloc=''` → `INVALID_URL` trompeur.

## Scénario d'échec

Le pilote colle un lien de partage TikTok `https://vm.tiktok.com/ZM.../` → `{"error": {"code": "UNSUPPORTED_PLATFORM", "message": "unsupported host: 'vm.tiktok.com'"}}`.

## Piste de résolution

Matcher par suffixe de domaine (`youtube.com`, `youtu.be`, `tiktok.com`, `instagram.com` + sous-domaines) au lieu d'une table exacte. Le hint `platform` reste l'échappatoire mais ne devrait pas être nécessaire.

## Pourquoi Sonnet

Passage d'un match exact à un match par suffixe + tests d'URL.

## ✅ Résolu (2026-07-06)

Matching par suffixe de domaine (m./music./vm./www. + sous-domaines) + support des URL sans schéma quand le 1er segment ressemble à un host.

Vérifié : suite backend verte (481 passed).
