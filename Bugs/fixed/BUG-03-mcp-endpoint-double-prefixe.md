# BUG-03 — Endpoint MCP réellement servi sur `/mcp/mcp`, pas `/mcp`

- **Zone** : façade MCP / montage
- **Fichier(s)** : `backend/src/role_builder/main.py:50` et `:221` ; `backend/src/role_builder/mcp_server/server.py:20`
- **Sévérité** : critique
- **Confiance** : haute (vérifié empiriquement)
- **Difficulté de correction** : **Sonnet**

## Problème

`FastMCP("roles")` garde son défaut `streamable_http_path="/mcp"` : l'app retournée par `mcp.streamable_http_app()` contient une route interne `/mcp`. `app.mount("/mcp", mcp_asgi_app)` ajoute un second préfixe. Le commentaire de `main.py` annonce « exposée à la passerelle sur /mcp », mais l'endpoint réel est `/mcp/mcp`.

## Scénario d'échec

Vérifié empiriquement : `POST /mcp` (initialize JSON-RPC) → 307 vers `/mcp/` → **404**. Seul `POST /mcp/mcp` atteint le transport. Toute passerelle configurée sur `/mcp` ne peut pas ouvrir de session. Aucun test ne couvre ce chemin (`test_mount.py` ne teste que `/health/`).

## Piste de résolution

`FastMCP("roles", streamable_http_path="/")` (ou `mcp.settings.streamable_http_path = "/"`) avant `streamable_http_app()`, ou monter à la racine. Ajouter un test qui POSTe réellement `initialize` sur `/mcp`.

## Pourquoi Sonnet

Un paramètre à changer + un test de non-régression.

## ✅ Résolu (2026-07-06)

FastMCP(streamable_http_path="/") : l'endpoint réel est désormais /mcp (vérifié empiriquement : POST /mcp → 200).

Vérifié : suite backend verte (481 passed).
