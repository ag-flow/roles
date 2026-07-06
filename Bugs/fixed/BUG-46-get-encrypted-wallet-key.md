# BUG-46 — `get()` exige `encrypted_wallet_key` même quand la wallet_key est en cache

- **Zone** : secrets Harpocrate / client
- **Fichier(s)** : `backend/src/role_builder/secrets/harpocrate/client.py:256`
- **Sévérité** : mineure
- **Confiance** : haute
- **Difficulté de correction** : **Sonnet**

## Problème

`enc_wk = base64.b64decode(data["encrypted_wallet_key"])` est exécuté inconditionnellement, avant toute tentative de déchiffrement. Si la réponse serveur d'un secret omet ce champ (cas où la wallet_key vient du cache et où le champ pourrait ne pas être renvoyé), `get()` lève un `KeyError` brut au lieu d'une exception SDK — alors même que le déchiffrement via cache aurait réussi.

## Scénario d'échec

Endpoint renvoyant un secret sans `encrypted_wallet_key` → `KeyError: 'encrypted_wallet_key'` non catché, remonte tel quel à l'appelant (dans `secret_store.read_value`, seuls `HarpocrateError`/`SecretDecryptError`/`SecretNotFound` sont attrapés → l'exception échappe).

## Piste de résolution

Ne lire `encrypted_wallet_key` que dans la branche de fallback (`except VaultDecryptionError`), avec `data.get(...)` et une exception SDK claire si absent.

## Pourquoi Sonnet

Déplacer une lecture de champ dans la branche fallback.

## ✅ Résolu (2026-07-06)

Réglé avec le refactor BUG-45 : _get_raw ne lit encrypted_wallet_key que dans la branche fallback (grant JWT) ; un secret déchiffrable via le cache dont la réponse l'omet ne lève plus KeyError.

Vérifié : suite backend verte (481 passed).
