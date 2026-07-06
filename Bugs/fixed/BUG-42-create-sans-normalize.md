# BUG-42 — `create()`/`create_placeholder()` n'appliquent pas `_normalize_name` (path-style)

- **Zone** : secrets Harpocrate / client
- **Fichier(s)** : `backend/src/role_builder/secrets/harpocrate/client.py:175` (et `:233`)
- **Sévérité** : majeure
- **Confiance** : moyenne
- **Difficulté de correction** : **Opus**

## Problème

Pour un secret path-style (nom contenant `/`), `create()` envoie le nom brut dans le body (`{"name": name}`), sans le passage par `_normalize_name`. Or toutes les opérations de lecture/écriture/suppression unitaires passent par `_resolve_id_if_pathstyle()` qui normalise le nom (`_normalize_name`, ajout du `/` initial) puis compare `s.get("name") == normalized`. Il y a donc asymétrie entre le nom écrit et le nom recherché à la relecture.

## Scénario d'échec

`secret_store._create_in_wallet` construit `path = f"roles/{secret_type}/{secret_id}"` (sans slash initial). `_vault_upsert` fait `put(path)` → première écriture → `create(path, value)` envoie `name="roles/…"`. À la relecture, `read_value` → `get("roles/…")` → `_resolve_id_if_pathstyle` normalise en `/roles/…` et cherche `name == "/roles/…"`. Si le serveur a stocké le nom tel qu'envoyé (sans slash), le lookup échoue → `SecretNotFound` → le secret est considéré « invalide, re-saisie requise » alors qu'il existe. Pire : un `put` ultérieur peut recréer un doublon.

## Piste de résolution

Appliquer `_normalize_name` au nom dans `create()` et `create_placeholder()` (ou côté serveur garantir la normalisation d'entrée), pour un traitement identique à celui de la résolution en lecture.

## Pourquoi Opus

La normalisation à ajouter est simple, mais il faut d'abord confirmer la convention de normalisation côté serveur Harpocrate (interaction avec un composant externe) pour ne pas introduire une double normalisation.

## ✅ Résolu (2026-07-06)

create() et create_placeholder() appliquent _normalize_name au nom, symétrique avec la résolution en lecture.

Vérifié : suite backend verte (481 passed).
