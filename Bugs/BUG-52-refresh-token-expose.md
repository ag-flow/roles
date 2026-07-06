# BUG-52 — `refreshToken` Keycloak exposé au JavaScript du navigateur via la session

- **Zone** : frontend (en sursis) / sécurité auth
- **Fichier(s)** : `frontend/src/auth.ts:124-128`
- **Sévérité** : majeure (sécurité)
- **Confiance** : haute
- **Difficulté de correction** : **Sonnet**

## Problème

Le callback `session` copie `token.refreshToken` dans l'objet session. Tout ce que retourne ce callback est servi par `GET /api/auth/session` et lisible par n'importe quel JS de la page (`useSession()`). L'`accessToken` y est nécessaire pour la WS, mais le `refreshToken` (longue durée, permet d'obtenir de nouveaux access tokens auprès de Keycloak) n'est utilisé nulle part côté client — il est exposé gratuitement. Cela contredit la justification du proxy (`route.ts`, lignes 10-13 : « éviter de sortir le token côté JS »).

## Scénario d'échec

N'importe quelle faille XSS (ou extension navigateur malveillante) lit `fetch('/api/auth/session')` et exfiltre un refresh token Keycloak valide ~30 jours → émission de tokens d'accès hors de tout contrôle de session.

## Piste de résolution

Supprimer `session.refreshToken = token.refreshToken` (le garder uniquement dans le JWT chiffré côté serveur, où un futur refresh flow l'utilisera).

## Pourquoi Sonnet

Une ligne + la déclaration de type.
