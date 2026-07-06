# BUG-55 — Timer de debounce de `KeySettings` jamais nettoyé au unmount

- **Zone** : frontend (en sursis) / React
- **Fichier(s)** : `frontend/src/app/my-stack/transcription-services/KeySettings.tsx:38-44`
- **Sévérité** : mineure
- **Confiance** : haute
- **Difficulté de correction** : **Sonnet**

## Problème

`handleSliderChange` planifie `persist()` à 500 ms dans `timerRef`, mais aucun cleanup `useEffect` n'annule ce timer au démontage du composant.

## Scénario d'échec

L'utilisateur bouge le slider « Workers » puis clique immédiatement « Supprimer » sur la clé (le composant est démonté quand `mutate()` retire la ligne) → 500 ms plus tard, `PATCH /api/transcription-keys/{id}` part sur une clé supprimée → 404 → `window.alert('Erreur de sauvegarde…')` surgit hors contexte + `setSaving` sur composant démonté.

## Piste de résolution

`useEffect(() => () => { if (timerRef.current) clearTimeout(timerRef.current); }, [])`.

## Pourquoi Sonnet

Un `useEffect` de cleanup.
