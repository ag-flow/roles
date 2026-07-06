# BUG-04 — Protection DNS-rebinding : 421 pour tout Host non-localhost (passerelle bloquée)

- **Zone** : façade MCP / sécurité transport
- **Fichier(s)** : `backend/src/role_builder/mcp_server/server.py:20`
- **Sévérité** : critique
- **Confiance** : haute (vérifié empiriquement)
- **Difficulté de correction** : **Opus**

## Problème

Dans mcp 1.28, `FastMCP(...)` avec `host="127.0.0.1"` (défaut) auto-active `TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*"])`. Toute requête MCP dont l'en-tête `Host` n'est pas localhost est rejetée **421 Misdirected Request** avant d'atteindre le transport.

## Scénario d'échec

Vérifié empiriquement : `POST /mcp/mcp` avec `Host: testserver` → log `Invalid Host header: testserver` → 421. En déploiement réel (compose expose `backend:8000`, host test1 `192.168.10.201:8000`, passerelle `wrk.yoops.org`), le Host ne sera jamais localhost : **100 % des appels de la passerelle échouent en 421.**

## Piste de résolution

Passer un `TransportSecuritySettings` explicite à `FastMCP` : protection désactivée si le réseau est privé/derrière la passerelle, ou `allowed_hosts` incluant les hosts de déploiement, pilotés par Settings.

## Pourquoi Opus

Le correctif minimal (désactiver) est trivial, mais rendre les hosts autorisés configurables proprement via Settings et décider de la posture de sécurité (derrière passerelle) demande une petite conception.

## ✅ Résolu (2026-07-06)

FastMCP(transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False)) : plus de 421 pour un Host non-localhost (vérifié : Host=gateway → 200). Façade protégée par MCPAuthMiddleware (BUG-34).

Vérifié : suite backend verte (481 passed).
