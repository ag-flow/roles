# BUG-36 — WebSocket /ws : déconnexion client jamais lue, exception de send ≠ WebSocketDisconnect

- **Zone** : routes HTTP / WebSocket
- **Fichier(s)** : `backend/src/role_builder/routes/websocket.py:51-67`
- **Sévérité** : mineure
- **Confiance** : haute
- **Difficulté de correction** : **Opus**

## Problème

La boucle ne fait jamais `ws.receive()` : la fermeture côté client n'est détectée que lorsqu'un send échoue (au plus tard au heartbeat 30 s). Or sous uvicorn 0.46, un send vers un client déconnecté lève `uvicorn.protocols.utils.ClientDisconnected` (sous-classe d'`OSError`), pas `starlette.websockets.WebSocketDisconnect` : le `except WebSocketDisconnect` ne l'attrape pas, l'exception remonte et uvicorn logge « Exception in ASGI application » (ERROR) à chaque déconnexion. Le `finally` fait bien l'unsubscribe (pas de fuite), mais la désinscription est retardée jusqu'à 30 s et chaque fermeture d'onglet produit une stacktrace ERROR.

## Scénario d'échec

L'utilisateur ferme l'onglet frontend → 0-30 s plus tard le heartbeat lève `ClientDisconnected` → stacktrace ERROR dans les logs à chaque fois ; monitoring pollué.

## Piste de résolution

Lire en parallèle (`asyncio.wait` sur `queue.get()` et `ws.receive()`) pour capter `websocket.disconnect`, et/ou attraper `(WebSocketDisconnect, OSError)` autour des sends.

## Pourquoi Opus

Restructuration de la boucle en deux tâches concurrentes (réception + envoi) avec arrêt propre.

## ✅ Résolu (2026-07-06)

Boucle refondue : ws.receive() concurrent (asyncio.wait) capte la fermeture immédiatement ; capture (WebSocketDisconnect, OSError).

Vérifié : suite backend verte (481 passed).
