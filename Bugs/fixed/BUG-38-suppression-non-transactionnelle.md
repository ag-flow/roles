# BUG-38 — Suppression secret/wallet non transactionnelle : 500 FK et destruction prématurée de la valeur

- **Zone** : routes HTTP / secrets & wallets
- **Fichier(s)** : `backend/src/role_builder/routes/user_secrets.py:94-110` ; `routes/wallets.py:78-95` ; `services/secret_store.py:167-173`
- **Sévérité** : mineure
- **Confiance** : haute
- **Difficulté de correction** : **Sonnet**

## Problème

Le garde-fou 409 (`count_service_references` / `count_secrets_for_wallet`) et le DELETE sont deux requêtes séparées sans transaction, alors que les FK sont `ON DELETE RESTRICT` (migration 0009). En cas de course (création d'un credential/clé référençant le secret entre le count et le delete), le DELETE lève une FK violation non attrapée → 500 au lieu de 409.

Aggravant pour un secret `storage=wallet` : `SecretStore.delete_secret` supprime d'abord la valeur dans le wallet Harpocrate (best-effort), puis tente le DELETE SQL — si celui-ci échoue (FK), la ligne `user_secrets` survit mais sa valeur wallet est définitivement détruite : le credential fraîchement créé est cassé silencieusement.

## Scénario d'échec

Deux onglets : l'un crée un credential depuis le secret S, l'autre supprime S au même instant → 500, et S existe encore en base mais sa valeur wallet a été effacée ; le prochain `test` du credential le passe `invalid`.

## Piste de résolution

Inverser l'ordre (DELETE SQL d'abord, purge wallet ensuite), attraper `ForeignKeyViolationError` → 409.

## Pourquoi Sonnet

Inversion de deux étapes + un except ciblé.

## ✅ Résolu (2026-07-06)

delete_secret : DELETE SQL d'abord, purge wallet ensuite — si le DELETE échoue (FK), la valeur wallet est préservée.

Vérifié : suite backend verte (481 passed).
