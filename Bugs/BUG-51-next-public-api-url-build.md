# BUG-51 — `NEXT_PUBLIC_API_URL` inliné au build : WS/API pointent sur localhost:8000 du client

- **Zone** : frontend (en sursis) / build & runtime
- **Fichier(s)** : `frontend/Dockerfile` (aucun `ARG NEXT_PUBLIC_API_URL`, seul `BACKEND_INTERNAL_URL` est passé) ; `docker-compose-dev.yml:89` ; `frontend/src/components/WebSocketProvider.tsx:8-9` ; `frontend/src/lib/api/client.ts:57`
- **Sévérité** : majeure
- **Confiance** : haute
- **Difficulté de correction** : **Opus**

## Problème

Les variables `NEXT_PUBLIC_*` sont substituées dans le bundle client **au `npm run build`** (stage builder du Dockerfile), pas au démarrage du conteneur. Le Dockerfile ne définit jamais `NEXT_PUBLIC_API_URL` au build ⇒ le bundle client contient le fallback `'http://localhost:8000'`. La ligne `NEXT_PUBLIC_API_URL: http://localhost:${BACKEND_PORT}` du compose est du code mort côté navigateur.

## Scénario d'échec

Déploiement via `dev-deploy.sh` sur le host `usage=ressources`, utilisateur qui ouvre `http://<host>:3000` depuis sa machine → le navigateur tente `ws://localhost:8000/ws?...` (sa propre machine) → connexion refusée → boucle de retry toutes les 3 s à l'infini, aucun événement temps réel. Seul le cas « navigateur sur le host Docker lui-même » fonctionne.

## Piste de résolution

Passer `ARG NEXT_PUBLIC_API_URL` + `ENV` dans le stage builder et l'injecter depuis `build.sh`, ou (mieux, cohérent avec le proxy) dériver l'URL WS de `window.location` — ce qui suppose d'exposer la WS via un chemin même-origine (le route handler Next ne proxifie pas l'upgrade WS, donc il faut un vrai reverse-proxy ou l'exposition directe du backend).

## Pourquoi Opus

Le fix build-arg est trivial, mais l'architecture « backend joignable seulement en LAN » documentée dans le proxy rend la WS structurellement inaccessible en prod tunnelée — décision d'archi requise.
