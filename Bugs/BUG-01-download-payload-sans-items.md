# BUG-01 — Payload `download` sans `items` : pipeline d'acquisition no-op marqué en succès

- **Zone** : services cœur / orchestrateur
- **Fichier(s)** : `backend/src/role_builder/services/scraper_orchestrator.py:147-165` (`_build_payload`), croisé avec `docker/scrapers/youtube/youtube/download.py:73-90` et `entrypoint.py:29-31`
- **Sévérité** : critique
- **Confiance** : haute
- **Difficulté de correction** : **Opus**

## Problème

`_build_payload` construit le même payload pour `discover` et `download` : `{task_id, command, url, options, output}` — jamais de champ `items`, et `job["source_item_id"]` est ignoré. Or `download.run` fait `items = task.get("items", [])` et boucle dessus (chaque item nécessite `item["id"]` et `item["url"]`). Avec `items=[]`, il émet `complete downloaded=0 failed=0` et retourne 0.

## Scénario d'échec

`roles__select_items` → `apply_selection` (`services/acquisition/selection.py:86-100`) enqueue un `scraping_job` `command="download"` par item → l'orchestrateur lance le container → le container ne télécharge rien, exit 0 → `mark_job_done`. L'item reste `pending_download`/`selected` pour toujours, aucun audio, aucun event `item_done`, aucune transcription. **Tout le pipeline d'acquisition V2 est un no-op silencieux marqué en succès.**

## Piste de résolution

Pour `command="download"`, inclure `items: [{id, url}]` dans le payload à partir de `source_item_id`. L'URL par item n'est pas stockée en DB : la dériver de `platform_item_id` selon la plateforme (ex. `https://www.youtube.com/watch?v={id}`) ou la persister au moment du discover. Aligner la spec 03 (le contrat stdin documenté ne contient pas `items` non plus). Couvrir le cas multi-items.

## Pourquoi Opus

Le contrat stdin est déclaré « figé » : il faut trancher côté backend (construction/stockage des URLs par plateforme), décider où reconstruire l'URL, et couvrir plusieurs plateformes + le batch multi-items. Ce n'est pas une correction locale d'une ligne.
