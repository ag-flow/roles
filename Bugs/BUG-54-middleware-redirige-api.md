# BUG-54 — Le middleware redirige les appels API non authentifiés vers la page HTML de login

- **Zone** : frontend (en sursis) / middleware
- **Fichier(s)** : `frontend/src/middleware.ts:5-8` et `:14` (matcher)
- **Sévérité** : mineure
- **Confiance** : haute
- **Difficulté de correction** : **Sonnet**

## Problème

Le matcher n'exclut que `api/auth` ; tous les autres `/api/*` (donc le proxy `[...path]`) passent par le middleware qui répond `Response.redirect('/login')` (302) quand `req.auth` est nul. `fetch` suit la redirection.

## Scénario d'échec

Cookie de session supprimé/expiré avec un onglet ouvert → `listSecrets()` reçoit finalement `GET /login` = 200 HTML → `resp.ok` vrai → `resp.json()` jette `SyntaxError: Unexpected token '<'` au lieu d'un 401 exploitable ; l'UI affiche une erreur générique et rien n'incite au re-login.

## Piste de résolution

Dans le middleware, pour `pathname.startsWith('/api/')`, retourner `new Response(null, { status: 401 })` au lieu d'une redirection (ou exclure `/api` du matcher et laisser le proxy renvoyer 401 quand `session` est nul).

## Pourquoi Sonnet

Une branche conditionnelle dans le middleware.
