# BUG-08 — WorkerManager : conflit de nom Docker au respawn (containers jamais supprimés)

- **Zone** : services cœur / worker manager
- **Fichier(s)** : `backend/src/role_builder/services/worker_manager.py:115-123` (`docker run -d --name` sans `--rm`), `:254` (`docker stop` sans `docker rm`), `:77` (`range(active, active + delta)`)
- **Sévérité** : majeure
- **Confiance** : haute
- **Difficulté de correction** : **Sonnet**

## Problème

Le nom `rb-worker-{user_id}-{provider}-{idx}` est déterministe, `docker run` n'a pas `--rm`, et `_stop_and_mark` fait seulement `docker stop`. Le container stoppé conserve son nom. Au respawn, `_count_active_workers` (statuts DB ≠ stopped/failed) redémarre l'index à `active`, donc réutilise un nom déjà pris → `docker run` échoue (« Conflict. The container name is already in use »), stdout vide → `RuntimeError` (ligne 137).

Même problème si le worker 0 est stoppé alors que le worker 1 tourne (index recalculé = 1 → collision avec le container **en marche**). En prime, `_stop_and_mark` marque `status='stopped'` en DB même quand `docker stop` a échoué (lignes 253-266) → container orphelin qui consomme la clé.

## Scénario d'échec

Spawn worker idx 0 → auto-stop après inactivité → nouvelle activité → `ensure_user_workers_running` → `RuntimeError`, plus aucun worker provisionnable pour ce user/provider sans `docker rm` manuel.

## Piste de résolution

Ajouter `docker rm -f` (ou `docker stop` + `docker rm`) dans `_stop_and_mark`, ou suffixer le nom d'un composant unique (timestamp/uuid court). Ne marquer `stopped` que si `docker stop` a réussi.

## Pourquoi Sonnet

Ajout d'un `docker rm` + garde sur le résultat du stop.

## ✅ Résolu (2026-07-06)

Nom de conteneur suffixé d'un uuid court (unicité au respawn) + docker rm après docker stop (libère le nom).

Vérifié : suite backend verte (481 passed).
