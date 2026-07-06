# BUG-40 — `_claims_to_user` : `sub` non-UUID → 500 sur un token pourtant valide

- **Zone** : auth / dépendances
- **Fichier(s)** : `backend/src/role_builder/auth/dependencies.py:71`
- **Sévérité** : mineure
- **Confiance** : moyenne
- **Difficulté de correction** : **Sonnet**

## Problème

`UUID(claims["sub"])` lève `ValueError` non attrapée si le `sub` n'est pas un UUID. Keycloak émet des UUID pour les users, mais pas nécessairement pour tous les types de tokens (fédération d'identité avec sub importé, brokers, certains service-accounts selon config) : le token passe la validation signature/claims puis provoque un 500 sur chaque requête, au lieu d'un 401 explicite.

## Scénario d'échec

Realm Keycloak avec identity broker conservant le `sub` amont (format non-UUID) → l'utilisateur se connecte, chaque appel API répond 500.

## Piste de résolution

Attraper `ValueError` dans `get_current_user`/`authenticate_websocket` → 401 « unsupported subject format », ou dériver un UUID (`uuid5`) du sub.

## Pourquoi Sonnet

Un try/except autour de la conversion.

## ✅ Résolu (2026-07-06)

_claims_to_user attrape ValueError/KeyError sur UUID(sub) → InvalidTokenError → 401 (au lieu de 500) ; l'appel est passé dans le try de get_current_user.

Vérifié : suite backend verte (481 passed).
