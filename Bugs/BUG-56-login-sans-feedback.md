# BUG-56 — Échec du login local-admin sans aucun feedback

- **Zone** : frontend (en sursis) / auth
- **Fichier(s)** : `frontend/src/app/login/page.tsx:63-71` (server action `signIn('local-admin', …)`)
- **Sévérité** : mineure
- **Confiance** : moyenne
- **Difficulté de correction** : **Sonnet**

## Problème

Avec Auth.js v5, un `authorize()` qui retourne `null` fait jeter `CredentialsSignin` par `signIn()` dans la server action ; l'action ne l'attrape pas et la page ne lit jamais `searchParams.error`. Selon le chemin (throw non attrapé vs redirection `/login?error=CredentialsSignin`), l'utilisateur obtient soit une page d'erreur Next générique, soit un retour silencieux au formulaire vierge.

## Scénario d'échec

Mot de passe local-admin erroné → aucun message « identifiants invalides », l'opérateur croit à une panne du backend.

## Piste de résolution

try/catch autour de `signIn` (`if (e instanceof AuthError) redirect('/login?error=credentials')`) et affichage du message quand `searchParams.error` est présent.

## Pourquoi Sonnet

try/catch + affichage conditionnel.
