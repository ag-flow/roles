# BUG-35 — Validation JWKS Keycloak bloquante dans l'event loop (urllib sync, timeout 30 s)

- **Zone** : auth / Keycloak
- **Fichier(s)** : `backend/src/role_builder/auth/keycloak.py:47-48` (et catch mort ligne 60)
- **Sévérité** : majeure
- **Confiance** : haute
- **Difficulté de correction** : **Sonnet**

## Problème

`PyJWKClient.get_signing_key_from_jwt` fait un `urllib.request.urlopen` synchrone (`timeout=30`) directement dans la coroutine `validate`, sans `to_thread`. Sur cache-miss (refresh toutes les 300 s côté PyJWT, recréation du client toutes les 3600 s côté code) l'event loop entier est gelé pendant le fetch. Si Keycloak est lent/injoignable, chaque requête authentifiée bloque tout le backend jusqu'à 30 s — y compris `/health`, les tools MCP et le relais WS. Accessoirement, le `except httpx.HTTPError` (ligne 60) est du code mort : PyJWT lève `PyJWKClientConnectionError` (une `PyJWTError`), jamais httpx.

## Scénario d'échec

Keycloak down (routage blackhole) → chaque requête portant un Bearer fige le process ~30 s ; le backend devient indisponible pour tous, workers compris.

## Piste de résolution

Envelopper `get_signing_key_from_jwt` dans `asyncio.to_thread(...)`, réduire le timeout via le constructeur `PyJWKClient`, supprimer le catch httpx mort.

## Pourquoi Sonnet

Un `to_thread` + un paramètre `timeout` + suppression de code mort.

## ✅ Résolu (2026-07-06)

get_signing_key_from_jwt exécuté via asyncio.to_thread + timeout PyJWKClient=5s ; catch httpx mort supprimé.

Vérifié : suite backend verte (481 passed).
