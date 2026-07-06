# BUG-53 — Aucun refresh de token : session 30 jours avec un accessToken expiré en minutes

- **Zone** : frontend (en sursis) / auth
- **Fichier(s)** : `frontend/src/auth.ts:109-122` (callback `jwt`)
- **Sévérité** : majeure
- **Confiance** : haute
- **Difficulté de correction** : **Opus**

## Problème

`expiresAt` et `refreshToken` sont stockés mais jamais utilisés : le callback `jwt` ne rafraîchit jamais l'access token et ne vérifie jamais son expiration. La session JWT NextAuth vit 30 jours (défaut) alors qu'un access token Keycloak vit typiquement 5-15 min, et le JWT local-admin 12 h (`LOCAL_ADMIN_TOKEN_TTL_S`).

## Scénario d'échec

Login Keycloak, l'utilisateur revient 20 minutes plus tard : `useSession()` dit « authenticated », le middleware laisse passer, mais chaque appel proxifié envoie un Bearer expiré → 401 backend sur toutes les pages (« Erreur de chargement ») sans aucune invite de reconnexion ; la WS est aussi refusée. L'utilisateur est coincé jusqu'à déconnexion manuelle.

## Piste de résolution

Dans le callback `jwt`, si `Date.now()/1000 > token.expiresAt`, jouer le refresh grant Keycloak (`grant_type=refresh_token`) et mettre à jour le token ; en échec, marquer `token.error` et forcer le re-login ; aligner `session.maxAge` sur la durée de vie réelle pour le mode local-admin.

## Pourquoi Opus

Flow de refresh OIDC + gestion d'erreur + alignement des durées + tests.
