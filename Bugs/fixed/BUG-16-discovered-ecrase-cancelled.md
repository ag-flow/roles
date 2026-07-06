# BUG-16 — Un event `discovered` tardif écrase le statut `cancelled`

- **Zone** : acquisition / auto-select
- **Fichier(s)** : `backend/src/role_builder/services/acquisition/auto_select.py:36-51`
- **Sévérité** : majeure
- **Confiance** : haute
- **Difficulté de correction** : **Sonnet**

## Problème

`on_discovery_complete` fait `update_status(request_key, "discovered")` (ou sélectionne + `"acquiring"` en mode auto) sans vérifier le statut courant de la requête. `cancel_request` n'annule que les jobs `pending`/`claimed` (`scraping_jobs.cancel_pending_claimed`) — un job discover déjà `processing` va au bout et son event `discovered` traverse ce chemin.

## Scénario d'échec

`submit_acquisition(mode="auto")` puis `cancel_request` pendant que le container discover tourne → à la fin de la découverte, la requête annulée repasse `acquiring`, tous les items matchés sont sélectionnés et des jobs download sont enqueués : **l'annulation est silencieusement défaite.**

## Piste de résolution

Dans `on_discovery_complete`, sortir immédiatement si `request["status"] == "cancelled"` (et idéalement faire l'update via un `UPDATE ... WHERE status <> 'cancelled'`).

## Pourquoi Sonnet

Une garde en tête de fonction + un `WHERE` conditionnel.

## ✅ Résolu (2026-07-06)

on_discovery_complete sort immédiatement si la requête est cancelled : un event discovered tardif ne défait plus l'annulation.

Vérifié : suite backend verte (481 passed).
