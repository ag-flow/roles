# BUG-27 — `item_ids` non-UUID → erreur de transport au lieu de l'enveloppe `{"error"}`

- **Zone** : façade MCP / adaptateurs (confirmé par 2 agents)
- **Fichier(s)** : `backend/src/role_builder/mcp_server/tools/admin.py:27` ; `mcp_server/tools/discovery.py:35`
- **Sévérité** : mineure
- **Confiance** : haute (vérifié empiriquement)
- **Difficulté de correction** : **Sonnet**

## Problème

`UUID(item_id)` est dans le `try`, mais seul `AcquisitionError` est catché ; `ValueError` remonte. Vérifié empiriquement : `roles__retry_failed(request_key, item_ids=["not-a-uuid"])` → `ToolError: Error executing tool roles__retry_failed: badly formed hexadecimal UUID string` (résultat `isError` MCP, fuite du message Python interne, pas l'enveloppe contractuelle §5.6). `upload.py` a pourtant `_parse_item_id` qui fait exactement la conversion correcte — incohérence interne.

## Scénario d'échec

Le pilote passe un item_id tronqué à `select_items`/`retry_failed` → erreur de transport non structurée au lieu de `{"error": {code, message, details}}`.

## Piste de résolution

Réutiliser le pattern `_parse_item_id` de `upload.py` (lever `AcquisitionError` avec un code type `INVALID_ITEM_ID`) dans `admin.py` et `discovery.py` — factoriser un helper partagé.

## Pourquoi Sonnet

Factorisation d'un helper existant + 2 tests.

## ✅ Résolu (2026-07-06)

mcp_server/tools/parsing.parse_item_ids lève INVALID_ITEM_ID (AcquisitionError) ; utilisé par admin.py et discovery.py.

Vérifié : suite backend verte (481 passed).
