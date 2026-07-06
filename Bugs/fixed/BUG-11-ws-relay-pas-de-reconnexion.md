# BUG-11 — WSRelay : aucune reconnexion si la connexion LISTEN asyncpg tombe

- **Zone** : services cœur / relais WebSocket
- **Fichier(s)** : `backend/src/role_builder/services/ws_relay.py:50-55`
- **Sévérité** : majeure
- **Confiance** : haute
- **Difficulté de correction** : **Opus**

## Problème

La connexion LISTEN est ouverte une seule fois au startup. asyncpg ne reconnecte pas et ne rejoue pas les `add_listener` ; en cas de perte de connexion (restart PG, coupure réseau, idle timeout d'un proxy), `_on_notify` ne sera plus jamais appelé. Aucun health-check (`_conn.is_closed()`), aucun mécanisme de retry.

## Scénario d'échec

Restart PostgreSQL → tous les clients WebSocket restent connectés (le heartbeat `ping` de `routes/websocket.py` continue) mais ne reçoivent plus jamais d'events, silencieusement, jusqu'au redémarrage du backend.

## Piste de résolution

Enregistrer un callback de terminaison (`conn.add_termination_listener`) ou une boucle de surveillance qui teste `is_closed()` et reconnecte avec backoff, en ré-enregistrant les listeners.

## Pourquoi Opus

Boucle de reconnexion avec backoff, ré-enregistrement des listeners, et tests de résilience (perte/reprise de connexion).

## ✅ Résolu (2026-07-06)

WSRelay.start() lance un moniteur (`_monitor`) qui détecte la coupure (`is_closed`) et reconnecte en ré-enregistrant les listeners ; stop() l'arrête proprement.

Vérifié : suite backend verte (481 passed).
