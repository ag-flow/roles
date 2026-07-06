# BUG-49 — minio_client : endpoint `host:port` sans schéma mal parsé (host = numéro de port)

- **Zone** : services cœur / MinIO
- **Fichier(s)** : `backend/src/role_builder/services/minio_client.py:33-42`
- **Sévérité** : mineure
- **Confiance** : haute
- **Difficulté de correction** : **Sonnet**

## Problème

Le fallback `netloc or parsed.path` est censé supporter un endpoint sans schéma, mais `urlparse("minio:9000")` donne `scheme='minio', path='9000'` → le client MinIO est construit avec host `'9000'`. Le fallback ne fonctionne que pour `IP:port` (`urlparse("192.168.1.5:9000")` → path=`'192.168.1.5:9000'`). Tout hostname alphabétique + port sans schéma — précisément le format natif attendu par minio-py — est cassé silencieusement à la première requête.

## Scénario d'échec

Un opérateur configure `MINIO_ENDPOINT=minio:9000` (convention MinIO standard) → toutes les opérations S3 échouent en résolution DNS de `'9000'`, sans message pointant la config.

## Piste de résolution

Si `"//" not in endpoint`, parser avec `urlparse("//" + endpoint)` ; ou valider/normaliser l'endpoint dans Settings (exiger un schéma explicite et lever sinon).

## Pourquoi Sonnet

Normalisation de l'endpoint avant parse.

## ✅ Résolu (2026-07-06)

Endpoint sans schéma (minio:9000) re-parsé avec préfixe // : le host n'est plus confondu avec le port.

Vérifié : suite backend verte (481 passed).
