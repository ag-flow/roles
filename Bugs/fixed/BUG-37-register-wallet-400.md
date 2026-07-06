# BUG-37 — Enregistrement wallet : panne réseau Harpocrate renvoyée en 400 « token refusé »

- **Zone** : services / secret_store + routes wallets
- **Fichier(s)** : `backend/src/role_builder/services/secret_store.py:79-84` ; `routes/wallets.py:59-60`
- **Sévérité** : mineure
- **Confiance** : haute
- **Difficulté de correction** : **Sonnet**

## Problème

`register_wallet` attrape `HarpocrateError` en bloc pour lever `InvalidWalletTokenError` → 400. Or le client Harpocrate embarqué (`secrets/harpocrate/http.py:166-173`) convertit les erreurs de connexion (`httpx.ConnectError`, `TimeoutException`) en `VaultHttpError(0, "Connection failed after N attempts")`, une `HarpocrateError`. Un serveur Harpocrate injoignable produit donc « 400 token refusé : Connection failed… » : code faux (devrait être 502/503 comme le fait déjà `create_secret` avec `WalletUnavailableError`) et message qui pousse l'utilisateur à re-saisir un token pourtant valide.

## Scénario d'échec

Harpocrate en maintenance → `POST /api/wallets` avec un token valide → 400 « token refusé » ; l'utilisateur régénère son token pour rien.

## Piste de résolution

Distinguer `VaultHttpError` avec status 0 (ou les erreurs de connexion) → `WalletUnavailableError` → 502 ; réserver 400 aux `InvalidTokenError`/`PermissionDenied`/`ValueError` de format.

## Pourquoi Sonnet

Affiner le tri des exceptions dans `register_wallet` + le catch 502 dans la route.

## ✅ Résolu (2026-07-06)

register_wallet distingue VaultHttpError status 0 (connexion) → WalletUnavailableError → 502 ; 400 réservé au token réellement refusé.

Vérifié : suite backend verte (481 passed).
