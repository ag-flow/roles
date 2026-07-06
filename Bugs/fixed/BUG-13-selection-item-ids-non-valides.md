# BUG-13 — `apply_selection`/`select_items` : item_ids d'une autre source acceptés, `selected_count` faux

- **Zone** : acquisition / sélection (MCP + REST)
- **Fichier(s)** : `backend/src/role_builder/services/acquisition/selection.py:85-97` ; `db_helpers/source_items.py:243` (exposé via `selection.py:80-83`)
- **Sévérité** : majeure
- **Confiance** : haute
- **Difficulté de correction** : **Sonnet**

## Problème

La boucle d'enqueue fait `get_by_id(item_id)` et ne vérifie que `item["status"] == "pending_download"` — jamais `item["source_id"] == source_id`. Le `UPDATE ... WHERE source_id = $1` de `select_items` protège le flag `selected`, mais pas la création de jobs : un `scraping_job` `command=download` est inséré avec le `source_id` de la requête courante et le `source_item_id` d'un item étranger.

De plus, le helper retourne `len(item_ids)` quel que soit le résultat des UPDATE : des UUID inconnus, des doublons, ou des ids d'une autre source gonflent `selected_count`.

## Scénario d'échec

`roles__select_items(request_key="yt-a-…", item_ids=[<id d'un item de la requête B>])` → job download incohérent (source A / item B, tenant_id de A), l'item de B est téléchargé sous les credentials et le contexte de A ; `get_active_job_for_item` marquera ensuite l'item de B « déjà en vol » côté B. La réponse annonce `selected_count: 1` même quand rien n'a été sélectionné.

## Piste de résolution

Dans la boucle, `continue` (ou lever `AcquisitionError("UNKNOWN_ITEM")`) si `item is None or item["source_id"] != source_id`. Retourner le rowcount réel de l'UPDATE (parser le tag `UPDATE <n>` de `conn.execute`, comme `_parse_update_count`).

## Pourquoi Sonnet

Une condition dans la boucle + parsing du tag d'UPDATE + tests.

## ✅ Résolu (2026-07-06)

apply_selection vérifie item.source_id == source_id ; select_items retourne le rowcount réel (parse du tag UPDATE), plus len(item_ids).

Vérifié : suite backend verte (481 passed).
