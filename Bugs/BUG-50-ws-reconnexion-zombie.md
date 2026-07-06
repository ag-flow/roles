# BUG-50 — Reconnexion WebSocket zombie après `disconnect()` + sockets dupliquées

- **Zone** : frontend (en sursis) / WebSocket
- **Fichier(s)** : `frontend/src/lib/ws/connection.ts:35-38` (onclose) et `:52-59` (disconnect)
- **Sévérité** : majeure
- **Confiance** : haute
- **Difficulté de correction** : **Sonnet**

## Problème

`disconnect()` annule le timer puis appelle `ws.close()`, mais le handler `onclose` du socket se déclenche APRÈS et replanifie inconditionnellement `setTimeout(() => this.openSocket(), 3000)`. Rien ne distingue une fermeture volontaire d'une coupure réseau. De plus `openSocket()` ne ferme jamais un socket existant avant d'en ouvrir un autre, et les deux sockets partagent la même map de listeners.

## Scénario d'échec

1. Logout ou unmount du `WebSocketProvider` → `disconnect()` → 3 s plus tard la WS se rouvre avec l'ancien token (URL figée dans `this.url`), connexion fantôme après déconnexion.
2. `reactStrictMode: true` (activé) : mount → cleanup → remount en dev produit un socket via `connect()` + un second via le reconnect zombie ; `this.ws` ne pointe que sur le dernier, l'autre fuit et **chaque événement est délivré deux fois** aux listeners (double `mutate()` SWR). Idem en prod à chaque changement d'`accessToken`.

## Piste de résolution

Flag `private closedByUser` positionné dans `disconnect()` et testé dans `onclose` ; dans `openSocket()`, fermer/neutraliser (`socket.onclose = null`) l'ancien socket avant d'en créer un nouveau ; annuler `reconnectTimer` dans `connect()`.

## Pourquoi Sonnet

Une dizaine de lignes dans une classe isolée.
