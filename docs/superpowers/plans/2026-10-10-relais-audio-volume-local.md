# Relais audio par volume local, et retrait du cycle d'upload — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** l'audio passe du scraper au worker de transcription par un **volume monté sur le host**, plus par MinIO ; et le cycle d'upload est retiré.

**Architecture :** le scraper écrit l'audio dans un répertoire que le payload lui désigne, au lieu de l'uploader puis de le supprimer. Le worker de transcription lit ce fichier sur disque, puis **le supprime** une fois la transcription réussie. Un balayeur ramasse les orphelins. Le cycle d'upload — seul autre producteur d'audio — est supprimé dans le même lot, pour que le worker n'ait **jamais** deux provenances à gérer.

**Tech Stack :** Python 3.12, asyncpg, pytest, yt-dlp, Docker.

**Spec :** `docs/specs/v3/00-cadrage-service-de-transcription.md` — décisions 10, 13, 15 et tension D.

## Périmètre : ce que ce plan ne fait PAS

Trois décisions du cadrage ne sont **pas tranchées**, et aucune tâche ici n'en dépend :

- **tension C** — simplification du module existant ou nouveau module. Ce lot est du **retrait**, valable dans les deux branches : les scrapers et le worker sont réutilisés quoi qu'il arrive.
- **l'ordre d'arrivée face à une chaîne de 300 vidéos** — décide la forme de la table de travail. Aucune table n'est créée ici.
- **ce que contient le résultat** — décide le format de la table de résultat. Le worker continue d'écrire son pivot dans `corpus-transcripts` comme aujourd'hui ; MinIO ne disparaît donc **pas** à la fin de ce lot.

Deux retraits du cadrage sont des plans **séparés**, et chacun est bloqué par autre chose :

- le **dépôt docflow** (décision 9) dépend du format de résultat ;
- le **provider `faster-whisper` local**, l'image `-cuda` et `docker-compose.pve2.yml` (décision 14)
  dépendent du **repli quand l'utilisateur n'a pas de clé** : les retirer rend toute transcription
  payante, et le pool `shared_default` aux clés admin était précisément le « pas de clés user =
  pas de coût ». Tant que ce point est ouvert, les retirer couperait le service pour qui n'a pas
  de clé.

Ce plan laisse donc MinIO en place pour les transcripts et le provider local fonctionnel. Il ne
change **que** le relais de l'audio, et retire le cycle d'upload parce qu'il est le second
producteur d'audio.

## Hypothèse explicitement posée (tension D)

La tension D — « qui supprime l'audio » — n'est pas tranchée par l'architecte, et la tâche 1 retire la ligne `local_path.unlink()` qui tenait le disque aujourd'hui. Ce plan pose donc : **le worker supprime le fichier après une transcription réussie** (tâche 4), **et** un balayeur ramasse les orphelins plus vieux que `audio_orphan_retention_h` (tâche 6). Si l'architecte tranche autrement, seules les tâches 4 et 6 bougent.

## Global Constraints

- Python 3.12, `from __future__ import annotations`, annotations partout.
- `async`/`await` partout ; **jamais** d'I/O bloquant dans un chemin asynchrone.
- `structlog.get_logger(__name__)` ; **jamais** `print()`. Aucun secret journalisé.
- Tout modèle de configuration porte `extra="forbid"`.
- Fichiers de **300 lignes maximum**.
- Migrations SQL **numérotées et immuables** dans `migrations/` ; dernière existante = `0011`.
- Aucune requête SQL construite par f-string ou concaténation.
- `uv run ruff check src/ tests/`, `uv run ruff format --check` et `uv run pytest` passent à chaque commit.
- Contrat scraper : **stdin JSON / stdout NDJSON**. Il change ici — `docs/specs/03-scrapers.md` est révisé **dans le même commit** que le code (tâche 1).

## Review Focus

Cinq classes d'entrée que le cadrage implique et qu'aucune tâche n'exerce spontanément. Chaque ligne a son test, posé dans la tâche qui porte le code.

1. **`output` d'une forme inattendue** envoyé à un scraper neuf (écart de version via `SCRAPER_IMAGE_TAG`) → event `error` explicite, **jamais** `KeyError`. → tâche 1.
2. **Répertoire de sortie absent ou non inscriptible** → échec bruyant **avant** de télécharger, pas après. → tâche 1.
3. **Le worker ne peut pas lire le fichier** que le scraper a écrit (uid/gid du bind mount) → job en erreur avec un message qui nomme le chemin et les droits. → tâche 4.
4. **Disque plein pendant le téléchargement** → `item_failed` avec un message exploitable, pas un `_exit` muet. → tâche 1.
5. **Rejeu d'un item déjà téléchargé** (retry après échec partiel) → pas de collision de nom de fichier, pas d'écrasement d'un fichier en cours de lecture. → tâche 1.

---

### Task 1: le scraper écrit dans le volume

**Files:**
- Modify: `docker/scrapers/youtube/youtube/download.py`
- Delete: `docker/scrapers/youtube/youtube/minio_uploader.py`
- Delete: `docker/scrapers/youtube/tests/test_minio_uploader.py`
- Modify: `docker/scrapers/base/requirements.txt` (retirer `minio>=7.2`)
- Modify: `docker/scrapers/youtube/pyproject.toml`, `uv.lock`
- Modify: `docs/specs/03-scrapers.md` (bloc `output` ligne ~69, event `item_done` ligne ~88, exemple ligne ~288)
- Test: `docker/scrapers/youtube/tests/test_download.py`

**Interfaces:**
- Consomme : rien.
- Produit : nouveau bloc `output` du payload stdin — `{"dir": str, "prefix": str, "format": str}`, **sans champ `type`** (décision 15) ; event `item_done` portant `audio_path: str` au lieu de `audio_s3_key`.

- [ ] **Step 1: Write the failing tests**

```python
def test_download_writes_audio_into_output_dir(tmp_path):
    # l'audio atterrit dans output.dir/prefix, et le fichier SURVIT à l'appel
def test_item_done_carries_audio_path_not_s3_key(tmp_path):
    assert "audio_path" in event and "audio_s3_key" not in event
def test_output_without_dir_emits_error_event(tmp_path):
    # écart de version : event {"type":"error", …}, et PAS de KeyError
def test_output_dir_not_writable_fails_before_download(tmp_path):
    # aucun appel à yt-dlp n'a été tenté
def test_replayed_item_does_not_clobber_existing_file(tmp_path):
    # deux passes sur le même item_id : pas d'écrasement en place
def test_disk_full_emits_item_failed_with_message(tmp_path):
    # yt-dlp en échec ENOSPC → item_failed, message non vide
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd docker/scrapers/youtube && uv run pytest tests/test_download.py -v`
Expected: FAIL (`audio_path` absent, `minio_uploader` encore appelé)

- [ ] **Step 3: Implement**

Dans `download.py` : `validate_output(output_cfg: dict[str, Any]) -> Path` en tête de `run()` — vérifie la présence de `dir`, son existence et son accessibilité en écriture, émet l'event `error` et rend un code non nul sinon. `_download_one` écrit dans `<dir>/<prefix><item_id>.<format>`, **ne supprime plus** le fichier, et émet `audio_path`. Supprimer l'import et le module `minio_uploader`.

Pour le rejeu (test 5) : écrire sous un nom temporaire puis `os.replace()` — atomique, donc un lecteur ne voit jamais un fichier partiel.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd docker/scrapers/youtube && uv run pytest -v && uv run ruff check youtube/ tests/`
Expected: PASS

- [ ] **Step 5: Réviser `docs/specs/03-scrapers.md`**

Le bloc `output`, l'event `item_done`, et l'exemple de payload. Corriger au passage le `prefix` documenté `"{tenant_id}/{role_id}/{source_id}/"` : `role_id` a été retiré par la migration 0011, le code construit `{tenant_id}/v2/{source_id}/`.

- [ ] **Step 6: Commit**

```bash
git add docker/scrapers docs/specs/03-scrapers.md
git commit -m "feat(scrapers): écrire l'audio dans le volume monté, retirer MinIO"
```

---

### Task 2: migration — `audio_s3_key` devient `audio_path`

**Files:**
- Create: `migrations/0012_audio_path.sql`
- Modify: `backend/src/role_builder/db_helpers/transcription_jobs.py`, `source_items.py`, `source_items_upload.py`
- Test: `backend/tests/test_migration_0012.py`

**Interfaces:**
- Produit : colonnes `audio_path` sur `transcription_jobs` et `source_items` ; `insert_job(..., audio_path: str, ...)`.

Le nom reste exact : une colonne nommée `audio_s3_key` contenant un chemin de fichier induirait en erreur pendant des années. Renommer une colonne exige une migration explicite et relue — ce n'est pas une réconciliation additive.

- [ ] **Step 1: Write the failing test**

```python
async def test_migration_0012_renames_audio_s3_key_to_audio_path(pool):
    # colonnes audio_path présentes, audio_s3_key absentes, sur les deux tables
async def test_migration_0012_replays_on_existing_database(pool):
    # base portant déjà des lignes : les valeurs sont conservées
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_migration_0012.py -v`
Expected: FAIL (migration absente)

- [ ] **Step 3: Écrire `migrations/0012_audio_path.sql`**

`ALTER TABLE … RENAME COLUMN` sur les deux tables, idempotent (`IF EXISTS` sur l'ancien nom). Vérifier d'abord que `0012` est **libre** — le dernier numéro présent est `0011`. Puis propager le nom dans les trois helpers.

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && uv run pytest tests/test_migration_0012.py -v`
Expected: PASS — sur base vierge **et** sur base existante

- [ ] **Step 5: Commit**

```bash
git add migrations/0012_audio_path.sql backend/src/role_builder/db_helpers backend/tests/test_migration_0012.py
git commit -m "feat(db): renommer audio_s3_key en audio_path"
```

---

### Task 3: l'orchestrateur envoie le nouveau `output` et consomme `audio_path`

**Files:**
- Modify: `backend/src/role_builder/services/scraper_orchestrator.py:210` (`_build_payload`) et son consommateur d'events
- Modify: `backend/src/role_builder/config.py` (ajouter `audio_volume_dir: str`)
- Test: `backend/tests/test_scraper_orchestrator.py`

**Interfaces:**
- Consomme : le contrat de la tâche 1 (`output` sans `type`, event `audio_path`), les colonnes de la tâche 2.
- Produit : `settings.audio_volume_dir` — chemin **dans le conteneur scraper**, monté depuis le host.

- [ ] **Step 1: Write the failing tests**

```python
def test_build_payload_output_has_dir_and_no_type():
    assert payload["output"]["dir"] and "type" not in payload["output"]
def test_build_payload_output_carries_no_credentials():
    # ni access_key, ni secret_key, ni endpoint — ils n'ont plus d'objet
async def test_item_done_event_persists_audio_path(pool):
```

- [ ] **Step 2: Run to verify they fail** — `cd backend && uv run pytest tests/test_scraper_orchestrator.py -v`

- [ ] **Step 3: Implement**

`_build_payload` rend `{"task_id", "command", "url", "options", "output": {"dir", "prefix", "format"}}`. Le `prefix` reste `{tenant_id}/v2/{source_id}/`. Le `docker run` du lancement reçoit en plus `-v <host_dir>:<audio_volume_dir>` **et** `--network <projet>_default` (sans lui, les conteneurs ne résolvent pas la base — second étage de BUG-02).

- [ ] **Step 4: Run to verify they pass**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(orchestrator): payload output sur volume local, plus de credentials MinIO"
```

---

### Task 4: le worker lit l'audio sur disque et le supprime après succès

**Files:**
- Modify: `docker/transcription-worker/worker/main.py:60-84`, `worker/minio_client.py`, `worker/config.py`
- Test: `docker/transcription-worker/tests/test_main.py`

**Interfaces:**
- Consomme : `job["audio_path"]` (tâche 2).
- Produit : `upload_transcript(s3_key, payload)` **inchangé** — le pivot reste dans `corpus-transcripts` tant que le format de résultat n'est pas tranché. `download_audio` disparaît.

`_build_transcript_s3_key` dérivait la clef du transcript de la clef audio par remplacement de `corpus-audio/`. Cette dérivation n'a plus de sens : la clef se construit maintenant depuis `source_item_id`.

- [ ] **Step 1: Write the failing tests**

```python
async def test_process_job_reads_audio_from_path_not_minio(tmp_path):
async def test_audio_file_deleted_after_successful_transcription(tmp_path):
async def test_audio_file_kept_when_transcription_fails(tmp_path):
    # sinon un retry n'a plus rien à transcrire
async def test_unreadable_audio_file_fails_job_with_path_and_perms(tmp_path):
    # Review Focus 3 : le message nomme le chemin ET les droits
```

- [ ] **Step 2: Run to verify they fail**

- [ ] **Step 3: Implement**

`process_job` lit `job["audio_path"]`, passe le fichier au provider, puis `Path(...).unlink(missing_ok=True)` **uniquement après** `mark_done`. Retirer `download_audio` et `AUDIO_BUCKET` de `minio_client.py`.

Garder le fichier en cas d'échec est délibéré : le retry doit retrouver l'audio. À commenter au point d'application, sinon quelqu'un « nettoiera » dans le `finally`.

- [ ] **Step 4: Run to verify they pass**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(worker): lire l'audio sur le volume, le supprimer après succès"
```

---

### Task 5: retrait du cycle d'upload

**Files:**
- Delete: `backend/src/role_builder/services/acquisition/upload/` (10 modules), `db_helpers/source_items_upload.py`, `mcp_server/tools/upload.py`
- Modify: `backend/src/role_builder/mcp_server/server.py` (retirer les 4 `add_tool`)
- Delete: les tests correspondants (`test_upload_*.py`, `upload_helpers.py`, `test_acceptance_upload.py`)
- Create: `migrations/0013_drop_upload_intake.sql`

**Interfaces:**
- Produit : la façade n'expose plus que 8 tools. Le worker n'a plus qu'**une** provenance d'audio — c'est la raison d'être de cette tâche dans ce lot.

- [ ] **Step 1: Write the failing test**

```python
async def test_mcp_server_exposes_no_upload_tools():
    assert not [t for t in tools if "upload" in t]
async def test_migration_0013_drops_upload_columns(pool):
```

- [ ] **Step 2: Run to verify they fail**

- [ ] **Step 3: Supprimer, puis écrire la migration**

Chercher les colonnes `upload_*` de `source_items` dans `0008_upload_intake.sql` avant d'écrire le `DROP` — ne pas se fier à la mémoire. Vérifier qu'aucun code restant ne les lit.

- [ ] **Step 4: Run the full suite**

Run: `cd backend && uv run pytest -q`
Expected: PASS, et **comparer l'ensemble des échecs** préexistants, pas leur nombre.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(mcp): retirer le cycle d'upload — plus qu'une provenance d'audio"
```

---

### Task 6: balayeur d'orphelins et garde disque

**Files:**
- Create: `backend/src/role_builder/services/audio_sweeper.py`
- Modify: `backend/src/role_builder/config.py` (`audio_orphan_retention_h: int = 48`, `audio_min_free_gb: int = 5`)
- Modify: `backend/src/role_builder/services/scheduler.py`
- Test: `backend/tests/services/test_audio_sweeper.py`

**Interfaces:**
- Consomme : `settings.audio_volume_dir` (tâche 3).
- Produit : `sweep_orphan_audio(*, now, pool) -> int` (nombre de fichiers supprimés).

La tâche 4 couvre le cas nominal. Celle-ci couvre ce qu'elle laisse : un job abandonné, un worker mort, un item `failed` définitivement. Sans elle, le disque de la VM dédiée se remplit et **arrête tout sans prévenir**.

- [ ] **Step 1: Write the failing tests**

```python
async def test_sweeper_removes_files_older_than_retention(tmp_path):
async def test_sweeper_keeps_files_of_jobs_still_pending(tmp_path):
    # valeur discriminante : un fichier vieux MAIS référencé par un job vivant
async def test_sweeper_logs_reclaimed_space(tmp_path):
async def test_orchestrator_refuses_new_job_below_min_free_gb(tmp_path):
    # fail closed : mieux vaut refuser que remplir le disque en silence
```

- [ ] **Step 2: Run to verify they fail**

- [ ] **Step 3: Implement**

Le balayeur ne supprime **que** les fichiers sans job vivant qui les référence — un fichier vieux mais attendu par un job `pending` reste. Journaliser l'espace récupéré : sans cette trace, on ne sait pas si la garde sert encore.

- [ ] **Step 4: Run to verify they pass**

- [ ] **Step 5: Mettre à jour `CLAUDE.md`** — retirer la mention de MinIO pour l'audio, nommer les trois nouveaux paramètres.

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(audio): balayeur d'orphelins et garde disque"
```
