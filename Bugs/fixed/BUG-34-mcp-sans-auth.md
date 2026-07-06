# BUG-34 — Façade MCP montée sans aucune authentification

- **Zone** : façade MCP / sécurité
- **Fichier(s)** : `backend/src/role_builder/main.py:221` (mount) ; `mcp_server/server.py` (aucune dépendance d'auth)
- **Sévérité** : majeure
- **Confiance** : haute
- **Difficulté de correction** : **Opus**

## Problème

Toute l'API REST exige un Bearer (`get_current_user`), mais la sous-app ASGI `/mcp` expose les tools `roles__*` (submit_acquisition, request_upload_slot → URL présignée PUT MinIO, cancel_request, get_corpus…) sans aucun contrôle : ni token, ni identité machine, ni allowlist réseau dans l'app. `docker-compose-dev.yml:82` publie le port 8000 sur l'hôte : tout client réseau peut soumettre des acquisitions, obtenir des slots d'upload MinIO ou annuler les requêtes d'autrui.

> Note : actuellement masqué par BUG-03 (endpoint sur `/mcp/mcp`) et BUG-04 (421 DNS-rebinding) ; dès que ces deux-là sont corrigés, l'absence d'auth devient exploitable.

## Scénario d'échec

`curl -X POST http://<host>:8000/mcp/mcp` avec une session streamable-http standard → appel de `roles__request_upload_slot` → URL présignée d'écriture dans le bucket audio, sans passer par la passerelle.

## Piste de résolution

Middleware ASGI d'auth sur le mount (token machine partagé avec la passerelle, ou vérification Bearer) ou binding réseau restreint (réseau docker interne uniquement, ne pas publier 8000).

## Pourquoi Opus

Le protocole streamable-http complique l'injection d'une dépendance FastAPI classique ; un middleware ASGI sur le mount + gestion du secret machine demande une petite conception.

## ✅ Résolu (2026-07-06)

MCPAuthMiddleware sur le mount /mcp : Bearer machine partagé, activé si settings.mcp_auth_token posé (pass-through sinon). Scopes non-http transmis.

Vérifié : suite backend verte (481 passed).
