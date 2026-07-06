# BUG-14 — Requête figée en `acquiring` pour toujours quand 0 item est sélectionné

- **Zone** : acquisition / statut
- **Fichier(s)** : `backend/src/role_builder/services/acquisition/status_shape.py:58-61` (avec `auto_select.py:44-51` et `intake.close_upload_request`)
- **Sévérité** : majeure
- **Confiance** : haute
- **Difficulté de correction** : **Sonnet**

## Problème

`derive_display_status` ne retourne `completed` que si `selected_total > 0`. Or deux chemins mettent le statut stocké à `acquiring` avec potentiellement 0 item sélectionné :
- (a) `mode=auto` dont les filtres ne matchent aucun item (`on_discovery_complete` applique une sélection vide puis force `acquiring`) ;
- (b) `close_upload_request` sur une requête sans aucun slot uploadé.

## Scénario d'échec

`submit_acquisition(mode="auto", filters={"since": "2027-01-01"})` → découverte OK, 0 item matché → `request_status` et `get_corpus.complete` renvoient `acquiring`/`false` indéfiniment ; le pilote pull en boucle sans fin.

## Piste de résolution

Si `selected_total == 0` et que le statut stocké est `acquiring`, dériver `completed` (corpus vide) — ou refuser/marquer `discovered` un `mode=auto` qui ne matche rien.

## Pourquoi Sonnet

Une branche dans `derive_display_status` + tests des deux chemins.

## ✅ Résolu (2026-07-06)

derive_display_status : selected_total==0 sur une requête acquiring → completed (corpus vide), plus de pull infini.

Vérifié : suite backend verte (481 passed).
