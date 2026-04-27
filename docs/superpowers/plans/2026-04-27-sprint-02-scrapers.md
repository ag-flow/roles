# Sprint 2 — Scrapers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pipeline d'acquisition end-to-end. À la fin de ce sprint, l'utilisateur peut créer un projet, ajouter une chaîne YouTube comme source, lancer la découverte, sélectionner des vidéos, et voir le téléchargement audio se faire en temps réel via WebSocket. Les fichiers MP3 (mono 16 kHz 32 kbps) atterrissent dans MinIO.

**Architecture:**
- **3 containers scrapers** Docker one-shot (YouTube + Instagram + TikTok), contrat stdin JSON / stdout NDJSON, exit code documenté.
- **Backend orchestrator** : pull `scraping_jobs` en FIFO avec `FOR UPDATE SKIP LOCKED`, fetch credentials OpenBao, lance les containers via `asyncio.create_subprocess_exec`, parse les events NDJSON, met à jour DB.
- **WebSocket relay** : asyncpg `add_listener` sur les 4 channels PG NOTIFY déjà câblés en Sprint 1, broadcast filtré par `tenant_id` aux clients WS connectés.
- **API REST** : endpoints sources/items/scraping-jobs.
- **Frontend** : onglet Sources avec table d'items filtrable, sélection multi, mises à jour live via WebSocket.

**Tech Stack:**
- Containers : `python:3.12-slim` + `yt-dlp>=2025.1.0` + `ffmpeg` + `minio>=7.2`
- Backend : asyncpg `add_listener` pour PG LISTEN, `asyncio.create_subprocess_exec` pour Docker, FastAPI `WebSocket`
- Frontend : SWR (à installer en E1) + WSManager natif `window.WebSocket` (cf. spec 10 § Patterns transverses)

**Décisions actées en amont** (cf. `docs/specs/12-open-decisions.md` § Scrapers + Sprint 2 émergentes) :
- Instagram : `yt-dlp` seul pour MVP, `gallery-dl` envisagé Phase 2 si qualité insuffisante
- Thumbnails : URL d'origine stockée dans `source_items.thumbnail_url`, pas d'upload MinIO
- Cap concurrent scrapers : env var `MAX_CONCURRENT_SCRAPERS=5` (configurable, défaut 5)
- Classification d'erreurs : MVP = tout `failed` + message en clair ; distinction `expired/geo/private` Phase 2
- Docker SDK : `asyncio.create_subprocess_exec("docker", ...)` conforme spec ; `aiodocker` envisagé Phase 2
- **OpenBao différé** : la fetch des cookies de scraping depuis OpenBao (`secret/scraping-credentials/...`) est REPORTÉE. Pour Sprint 2, l'orchestrator passe au container un `YOUTUBE_COOKIES_B64` optionnel via env var (vide par défaut). Les contenus publics fonctionnent sans cookies. Le rebranchage OpenBao se fera quand le sprint "Ma stack" (spec 07) introduira la CRUD `user_credentials`.

**Checkpoints d'exécution prévus** (à confirmer avant de lancer) :
- ✅ Fin Phase B (containers prêts, build local possible) — checkpoint léger
- ⚠️ **Fin Phase B / avant Phase C** — checkpoint humain explicite avant l'instanciation des containers Docker depuis le backend (Phase C "orchestrator"). À ce moment l'utilisateur valide la stratégie env var temporaire vs alternative.
- ✅ Fin Phase D (WebSocket relay câblé) — checkpoint léger
- ✅ Fin Phase F (UI sources prête) — checkpoint avant smoke test e2e

**Critères de fin** (cf. `docs/specs/03-scrapers.md` § Critères de fin de sprint) :
- Image `agflow-scraper-base` build sans erreur
- Image `agflow-scraper-youtube` build et fonctionne en standalone (test manuel)
- L'app peut créer une source, lancer un discover, lister les items
- Sélection d'items et lancement d'ingestion produisent des `scraping_jobs` puis des fichiers audio dans MinIO
- WebSocket pousse les events au front en temps réel
- Test avec une chaîne YouTube de 10+ vidéos : tout est ingéré sans crash
- Anti-ban actif (sleep_interval respecté, vérifié dans les logs)
- Containers Instagram et TikTok au moins squelettés (peuvent être simplifiés en MVP, mais le contrat NDJSON doit être respecté)

---

## File Structure

```
agflow.roles/
├── docker/
│   ├── scrapers/
│   │   ├── base/
│   │   │   ├── Dockerfile                        # Phase A1
│   │   │   └── requirements.txt                  # Phase A1
│   │   ├── youtube/
│   │   │   ├── Dockerfile                        # Phase A2
│   │   │   ├── pyproject.toml                    # Phase A2 (pour pytest)
│   │   │   ├── youtube/
│   │   │   │   ├── __init__.py                   # Phase A2
│   │   │   │   ├── entrypoint.py                 # Phase A2
│   │   │   │   ├── events.py                     # Phase A3
│   │   │   │   ├── discover.py                   # Phase A4
│   │   │   │   ├── download.py                   # Phase A5
│   │   │   │   └── minio_uploader.py             # Phase A6
│   │   │   └── tests/
│   │   │       ├── __init__.py                   # Phase A2
│   │   │       ├── test_events.py                # Phase A3
│   │   │       ├── test_discover.py              # Phase A4
│   │   │       ├── test_download.py              # Phase A5
│   │   │       └── test_minio_uploader.py        # Phase A6
│   │   ├── instagram/                            # Phase B1
│   │   │   ├── Dockerfile
│   │   │   └── instagram/__init__.py + entrypoint.py
│   │   └── tiktok/                               # Phase B2
│   │       ├── Dockerfile
│   │       └── tiktok/__init__.py + entrypoint.py
│
├── backend/
│   ├── src/role_builder/
│   │   ├── config.py                             # Phase C1 (modify : ajout MAX_CONCURRENT_SCRAPERS, scraper image tag)
│   │   ├── main.py                               # Phase C5 + D2 + E2 (modify : add routes + WS + lifespan)
│   │   ├── db_helpers/
│   │   │   ├── __init__.py                       # Phase C1
│   │   │   ├── sources.py                        # Phase C1
│   │   │   ├── source_items.py                   # Phase C1
│   │   │   ├── scraping_jobs.py                  # Phase C1
│   │   │   └── credentials.py                    # Phase C1
│   │   ├── services/
│   │   │   ├── docker_runner.py                  # Phase C2
│   │   │   ├── scraper_orchestrator.py           # Phase C3
│   │   │   ├── event_handlers.py                 # Phase C4
│   │   │   └── ws_relay.py                       # Phase D1
│   │   ├── schemas/
│   │   │   ├── __init__.py                       # Phase E1
│   │   │   ├── sources.py                        # Phase E1
│   │   │   └── items.py                          # Phase E1
│   │   └── routes/
│   │       ├── sources.py                        # Phase E2
│   │       ├── scraping_jobs.py                  # Phase E3
│   │       └── websocket.py                      # Phase D2
│   └── tests/
│       ├── test_db_helpers_sources.py            # Phase C1
│       ├── test_db_helpers_source_items.py       # Phase C1
│       ├── test_db_helpers_scraping_jobs.py      # Phase C1
│       ├── test_db_helpers_credentials.py        # Phase C1
│       ├── test_docker_runner.py                 # Phase C2
│       ├── test_scraper_orchestrator.py          # Phase C3
│       ├── test_event_handlers.py                # Phase C4
│       ├── test_ws_relay.py                      # Phase D1
│       ├── test_websocket_route.py               # Phase D2
│       └── test_sources_route.py                 # Phase E2
│
├── frontend/
│   ├── package.json                              # Phase F1 (modify : ajout swr)
│   └── src/
│       ├── lib/
│       │   ├── api/
│       │   │   ├── sources.ts                    # Phase F2
│       │   │   └── items.ts                      # Phase F2
│       │   ├── ws/
│       │   │   ├── connection.ts                 # Phase F3
│       │   │   └── hooks.ts                      # Phase F3
│       │   └── types.ts                          # Phase F2
│       ├── app/projects/[id]/sources/
│       │   ├── page.tsx                          # Phase F4 (sources list)
│       │   └── [sourceId]/
│       │       ├── page.tsx                      # Phase F5
│       │       ├── DiscoverButton.tsx            # Phase F5
│       │       ├── ItemsTable.tsx                # Phase F5
│       │       ├── ItemsFilters.tsx              # Phase F5
│       │       └── SelectionActions.tsx          # Phase F5
│       └── __tests__/
│           ├── sources.test.ts                   # Phase F2
│           └── ws-manager.test.ts                # Phase F3
│
└── scripts/
    └── build_scrapers.sh                         # Phase A7 (build local des images)
```

**Total** : ~55 fichiers à créer + ~3 modifications de fichiers existants.

---

# Phase A — Scraper YouTube de référence

Objectif : un container `agflow-scraper-youtube` complet, testé unitairement, qui lit une tâche JSON sur stdin et émet des events NDJSON sur stdout. Il sert de référence pour les autres scrapers (Phase B). Ne nécessite pas Docker pour les tests (mocked subprocess yt-dlp).

## Task A1 : Image de base scrapers

**Files:**
- Create: `docker/scrapers/base/Dockerfile`
- Create: `docker/scrapers/base/requirements.txt`

- [ ] **Step 1: Créer `docker/scrapers/base/requirements.txt`**

```
yt-dlp>=2025.1.0
minio>=7.2
pydantic>=2.5
structlog>=24.1
```

- [ ] **Step 2: Créer `docker/scrapers/base/Dockerfile`**

```dockerfile
FROM python:3.12-slim

# ffmpeg requis par yt-dlp pour l'extraction audio
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY base/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Le code spécifique à chaque plateforme est ajouté par les Dockerfiles enfants.
```

- [ ] **Step 3: Commit**

```bash
git add docker/scrapers/base/Dockerfile docker/scrapers/base/requirements.txt
git commit -m "$(cat <<'EOF'
chore(scrapers): image base (python 3.12-slim + ffmpeg + yt-dlp + minio + structlog)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

## Task A2 : Squelette package YouTube + entrypoint

**Files:**
- Create: `docker/scrapers/youtube/youtube/__init__.py`
- Create: `docker/scrapers/youtube/youtube/entrypoint.py`
- Create: `docker/scrapers/youtube/tests/__init__.py`
- Create: `docker/scrapers/youtube/pyproject.toml`
- Create: `docker/scrapers/youtube/Dockerfile`

> **Note** : `pyproject.toml` est nécessaire pour exécuter pytest localement (sans Docker) sur le code du container. Les tests sont la valeur ; le container final est juste l'emballage Docker.

- [ ] **Step 1: Créer `docker/scrapers/youtube/pyproject.toml`**

```toml
[project]
name = "agflow-scraper-youtube"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "yt-dlp>=2025.1.0",
    "minio>=7.2",
    "pydantic>=2.5",
    "structlog>=24.1",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.2",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["youtube"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Créer les `__init__.py`**

`docker/scrapers/youtube/youtube/__init__.py` :
```python
"""YouTube scraper package. Container one-shot pour discover/download via yt-dlp."""
```

`docker/scrapers/youtube/tests/__init__.py` : (fichier vide)

- [ ] **Step 3: Créer `docker/scrapers/youtube/youtube/entrypoint.py` (squelette dispatch)**

```python
"""YouTube scraper entrypoint.

Reads a task from stdin (JSON), dispatches to discover or download,
emits NDJSON events on stdout, exits with documented codes (cf. spec 03 § Codes de sortie).
"""
from __future__ import annotations

import asyncio
import json
import sys


async def main() -> int:
    """Read task from stdin and execute."""
    task_json = sys.stdin.read()
    try:
        task = json.loads(task_json)
    except json.JSONDecodeError as exc:
        print(json.dumps({"type": "error", "error": f"invalid JSON: {exc}"}), flush=True)
        return 1

    task_id = task.get("task_id", "unknown")
    print(json.dumps({"type": "started", "task_id": task_id}), flush=True)

    command = task.get("command")
    if command == "discover":
        from youtube import discover
        return await discover.run(task)
    elif command == "download":
        from youtube import download
        return await download.run(task)
    else:
        print(json.dumps({"type": "error", "error": f"unknown command: {command}"}), flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

> Les imports `from youtube import discover/download` sont locaux (à l'intérieur de `main()`) pour permettre le test du dispatcher sans avoir encore implémenté les sous-modules.

- [ ] **Step 4: Créer `docker/scrapers/youtube/Dockerfile`**

```dockerfile
FROM agflow-scraper-base:latest

COPY youtube/ /app/youtube/

ENTRYPOINT ["python", "-m", "youtube.entrypoint"]
```

- [ ] **Step 5: Initialiser uv et vérifier le squelette**

Run: `cd docker/scrapers/youtube && uv sync --extra dev`

Expected: `uv` télécharge les deps et crée `.venv/`. Pas d'erreur.

- [ ] **Step 6: Commit**

```bash
git add docker/scrapers/youtube/pyproject.toml \
        docker/scrapers/youtube/Dockerfile \
        docker/scrapers/youtube/youtube/__init__.py \
        docker/scrapers/youtube/youtube/entrypoint.py \
        docker/scrapers/youtube/tests/__init__.py \
        docker/scrapers/youtube/uv.lock
git commit -m "$(cat <<'EOF'
chore(scrapers): squelette package youtube (pyproject + entrypoint dispatch + Dockerfile)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

## Task A3 : Module `events.py` (NDJSON emitter)

**Files:**
- Create: `docker/scrapers/youtube/youtube/events.py`
- Create: `docker/scrapers/youtube/tests/test_events.py`

- [ ] **Step 1: Écrire le test qui échoue**

`docker/scrapers/youtube/tests/test_events.py` :
```python
"""Tests for the NDJSON event emitter."""
from __future__ import annotations

import io
import json

import pytest


def test_emit_writes_single_line_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """emit writes one NDJSON line to stdout per call."""
    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)

    from youtube.events import emit

    emit("started", task_id="abc")
    emit("progress", item_id="xyz", phase="downloading", percent=42)

    lines = buf.getvalue().strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"type": "started", "task_id": "abc"}
    assert json.loads(lines[1]) == {
        "type": "progress",
        "item_id": "xyz",
        "phase": "downloading",
        "percent": 42,
    }


def test_emit_flushes_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    """emit flushes after every line so the orchestrator sees events live."""
    flushed = []

    class _SpyStream:
        def write(self, s: str) -> int:
            return len(s)

        def flush(self) -> None:
            flushed.append(True)

    monkeypatch.setattr("sys.stdout", _SpyStream())

    from youtube.events import emit

    emit("complete", downloaded=10, failed=0)
    assert flushed == [True]
```

- [ ] **Step 2: Vérifier que le test échoue**

Run: `cd docker/scrapers/youtube && uv run pytest tests/test_events.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'youtube.events'`.

- [ ] **Step 3: Écrire l'implémentation**

`docker/scrapers/youtube/youtube/events.py` :
```python
"""NDJSON event emitter on stdout (contract: spec 03 § Format des events NDJSON)."""
from __future__ import annotations

import json
import sys
from typing import Any


def emit(event_type: str, **fields: Any) -> None:
    """Write one NDJSON event line to stdout and flush immediately.

    Format: {"type": <event_type>, ...fields}
    Always one event per line (NDJSON).
    """
    payload = {"type": event_type, **fields}
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()
```

- [ ] **Step 4: Vérifier que les tests passent**

Run: `cd docker/scrapers/youtube && uv run pytest tests/test_events.py -v`

Expected: PASS — 2 tests verts.

- [ ] **Step 5: Commit**

```bash
git add docker/scrapers/youtube/youtube/events.py docker/scrapers/youtube/tests/test_events.py
git commit -m "$(cat <<'EOF'
feat(scrapers): emitter NDJSON events youtube (emit type + fields, flush immédiat)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

## Task A4 : Module `discover.py` (yt-dlp metadata extraction)

**Files:**
- Create: `docker/scrapers/youtube/youtube/discover.py`
- Create: `docker/scrapers/youtube/tests/test_discover.py`

> **Note de stratégie** : `discover` invoque `yt-dlp --dump-json --flat-playlist URL` pour lister les vidéos d'une chaîne/playlist sans télécharger. Test : on stub `asyncio.create_subprocess_exec` pour simuler la sortie yt-dlp et on vérifie que `discover.run` parse correctement et émet le bon event NDJSON.

- [ ] **Step 1: Écrire le test qui échoue**

`docker/scrapers/youtube/tests/test_discover.py` :
```python
"""Tests for the discover command (channel/playlist enumeration)."""
from __future__ import annotations

import io
import json
from typing import Any

import pytest


class _StubProcess:
    def __init__(self, stdout_lines: list[str], returncode: int = 0) -> None:
        self._stdout = stdout_lines
        self.returncode = returncode

    async def communicate(self) -> tuple[bytes, bytes]:
        return ("\n".join(self._stdout).encode(), b"")


async def _make_subprocess(stdout_lines: list[str], returncode: int = 0) -> Any:
    async def _factory(*args: Any, **kwargs: Any) -> _StubProcess:
        return _StubProcess(stdout_lines, returncode)

    return _factory


@pytest.mark.asyncio
async def test_discover_emits_discovered_event_with_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """discover.run parses yt-dlp output and emits a 'discovered' event."""
    stdout_lines = [
        json.dumps({"id": "v1", "title": "Vidéo 1", "duration": 612, "upload_date": "20240101", "thumbnail": "http://t/v1.jpg"}),
        json.dumps({"id": "v2", "title": "Vidéo 2", "duration": 320, "upload_date": "20240115", "thumbnail": "http://t/v2.jpg"}),
    ]
    factory = await _make_subprocess(stdout_lines, returncode=0)
    monkeypatch.setattr("asyncio.create_subprocess_exec", factory)

    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)

    from youtube import discover

    task = {
        "task_id": "t-1",
        "url": "https://youtube.com/@Channel",
        "options": {"max_items": 100, "since_date": None},
    }
    rc = await discover.run(task)
    assert rc == 0

    events = [json.loads(line) for line in buf.getvalue().strip().split("\n")]
    discovered = next(e for e in events if e["type"] == "discovered")
    assert discovered["total"] == 2
    assert discovered["items"][0]["id"] == "v1"
    assert discovered["items"][0]["duration_s"] == 612
    assert discovered["items"][0]["published_at"] == "2024-01-01T00:00:00Z"
    assert discovered["items"][0]["thumbnail_url"] == "http://t/v1.jpg"


@pytest.mark.asyncio
async def test_discover_emits_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    """discover.run emits 'complete' after listing."""
    factory = await _make_subprocess([json.dumps({"id": "v1", "title": "T", "duration": 60})], returncode=0)
    monkeypatch.setattr("asyncio.create_subprocess_exec", factory)

    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)

    from youtube import discover

    rc = await discover.run({"task_id": "t-2", "url": "https://yt.com/c", "options": {}})
    assert rc == 0
    events = [json.loads(line) for line in buf.getvalue().strip().split("\n")]
    assert events[-1] == {"type": "complete", "discovered": 1}


@pytest.mark.asyncio
async def test_discover_returns_2_on_yt_dlp_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """discover.run returns exit code 2 when yt-dlp exits non-zero."""
    factory = await _make_subprocess(["[]"], returncode=1)
    monkeypatch.setattr("asyncio.create_subprocess_exec", factory)

    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)

    from youtube import discover

    rc = await discover.run({"task_id": "t-3", "url": "https://yt.com/c", "options": {}})
    assert rc == 2
```

- [ ] **Step 2: Vérifier que le test échoue**

Run: `cd docker/scrapers/youtube && uv run pytest tests/test_discover.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'youtube.discover'`.

- [ ] **Step 3: Écrire l'implémentation**

`docker/scrapers/youtube/youtube/discover.py` :
```python
"""Discover command : enumerate videos in a channel/playlist via yt-dlp --flat-playlist."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from youtube.events import emit


def _format_published_at(upload_date: str | None) -> str | None:
    """Convert yt-dlp 'upload_date' (YYYYMMDD) to ISO8601 UTC."""
    if not upload_date or len(upload_date) != 8:
        return None
    return f"{upload_date[0:4]}-{upload_date[4:6]}-{upload_date[6:8]}T00:00:00Z"


async def run(task: dict[str, Any]) -> int:
    """Discover items from a YouTube channel/playlist URL.

    Spec : docs/specs/03-scrapers.md § Format de tâche stdin (command: 'discover').
    """
    url = task["url"]
    options = task.get("options", {})
    max_items = options.get("max_items", 100)

    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--dump-json",
        "--playlist-end", str(max_items),
        url,
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _stderr = await proc.communicate()

    if proc.returncode != 0:
        emit("error", error=f"yt-dlp exited {proc.returncode}")
        return 2

    items: list[dict[str, Any]] = []
    for raw in stdout.decode("utf-8", errors="replace").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            continue
        items.append({
            "id": item.get("id"),
            "title": item.get("title"),
            "duration_s": item.get("duration"),
            "published_at": _format_published_at(item.get("upload_date")),
            "thumbnail_url": item.get("thumbnail"),
        })

    emit("discovered", total=len(items), items=items)
    emit("complete", discovered=len(items))
    return 0
```

- [ ] **Step 4: Vérifier que les tests passent**

Run: `cd docker/scrapers/youtube && uv run pytest tests/test_discover.py -v`

Expected: PASS — 3 tests verts.

- [ ] **Step 5: Commit**

```bash
git add docker/scrapers/youtube/youtube/discover.py docker/scrapers/youtube/tests/test_discover.py
git commit -m "$(cat <<'EOF'
feat(scrapers): youtube.discover (yt-dlp --flat-playlist + parse + events NDJSON)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

## Task A5 : Module `download.py` (audio extraction + upload)

**Files:**
- Create: `docker/scrapers/youtube/youtube/download.py`
- Create: `docker/scrapers/youtube/tests/test_download.py`

> Le download :
> 1. Pour chaque `item_id` dans `task["items"]`, lance `yt-dlp -x --audio-format mp3 ...` vers `/tmp/{item_id}.mp3`.
> 2. Upload le MP3 vers MinIO via le module `minio_uploader` (Phase A6).
> 3. Émet `progress` puis `item_done` ou `item_failed`.
> 4. Émet `complete` à la fin avec stats.
>
> Les tests stubbent à la fois `asyncio.create_subprocess_exec` (yt-dlp) et l'upload MinIO. On vérifie le séquencement des events et la gestion d'erreur item-par-item.

- [ ] **Step 1: Écrire le test qui échoue**

`docker/scrapers/youtube/tests/test_download.py` :
```python
"""Tests for the download command."""
from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest


class _StubProcess:
    def __init__(self, returncode: int) -> None:
        self.returncode = returncode

    async def communicate(self) -> tuple[bytes, bytes]:
        return (b"", b"")


def _patch_subprocess(monkeypatch: pytest.MonkeyPatch, returncodes: list[int]) -> None:
    """Patch asyncio.create_subprocess_exec to return queued returncodes."""
    queue = list(returncodes)

    async def _factory(*args: Any, **kwargs: Any) -> _StubProcess:
        rc = queue.pop(0) if queue else 0
        return _StubProcess(rc)

    monkeypatch.setattr("asyncio.create_subprocess_exec", _factory)


def _patch_minio(monkeypatch: pytest.MonkeyPatch, calls: list[dict[str, Any]]) -> None:
    """Patch upload_audio to record calls without doing real upload."""
    def _fake_upload(local_path: Path, output_cfg: dict[str, Any], item_id: str) -> str:
        calls.append({"path": str(local_path), "item_id": item_id, "output": output_cfg})
        return f"{output_cfg['prefix']}{item_id}.mp3"

    monkeypatch.setattr("youtube.minio_uploader.upload_audio", _fake_upload)


def _patch_filesystem(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Make sure the produced file 'exists' so download.run doesn't bail out."""
    real_unlink = Path.unlink

    def _ensure_exists(self: Path, missing_ok: bool = False) -> None:
        if not self.exists():
            self.write_bytes(b"fake audio")
        return real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", _ensure_exists)
    monkeypatch.setattr("youtube.download._tmp_dir", lambda: tmp_path)


@pytest.mark.asyncio
async def test_download_uploads_each_item_and_emits_done(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """download.run downloads each item and uploads to MinIO, emitting item_done."""
    _patch_subprocess(monkeypatch, [0, 0])
    calls: list[dict[str, Any]] = []
    _patch_minio(monkeypatch, calls)
    _patch_filesystem(monkeypatch, tmp_path)

    # Pre-create the expected files
    (tmp_path / "v1.mp3").write_bytes(b"audio1")
    (tmp_path / "v2.mp3").write_bytes(b"audio2")

    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)

    from youtube import download

    task = {
        "task_id": "t-1",
        "items": [
            {"id": "v1", "url": "https://youtube.com/watch?v=v1"},
            {"id": "v2", "url": "https://youtube.com/watch?v=v2"},
        ],
        "options": {"audio_format": "mp3"},
        "output": {
            "type": "minio",
            "endpoint": "http://minio:9000",
            "bucket": "corpus-audio",
            "prefix": "tenant/role/source/",
            "access_key": "k",
            "secret_key": "s",
        },
    }
    rc = await download.run(task)
    assert rc == 0

    events = [json.loads(line) for line in buf.getvalue().strip().split("\n")]
    done_events = [e for e in events if e["type"] == "item_done"]
    assert len(done_events) == 2
    assert done_events[0]["item_id"] == "v1"
    assert done_events[0]["audio_s3_key"] == "tenant/role/source/v1.mp3"

    assert len(calls) == 2
    assert calls[0]["item_id"] == "v1"


@pytest.mark.asyncio
async def test_download_emits_item_failed_on_yt_dlp_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """A non-zero yt-dlp returncode emits item_failed, not item_done."""
    _patch_subprocess(monkeypatch, [1])
    _patch_minio(monkeypatch, [])
    _patch_filesystem(monkeypatch, tmp_path)

    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)

    from youtube import download

    task = {
        "task_id": "t-2",
        "items": [{"id": "vbad", "url": "https://yt/watch?v=vbad"}],
        "output": {"type": "minio", "endpoint": "x", "bucket": "b", "prefix": "p/",
                   "access_key": "k", "secret_key": "s"},
    }
    rc = await download.run(task)
    # Partial failure : exit code 3 (cf. spec § Codes de sortie)
    assert rc == 3

    events = [json.loads(line) for line in buf.getvalue().strip().split("\n")]
    failed = [e for e in events if e["type"] == "item_failed"]
    assert len(failed) == 1
    assert failed[0]["item_id"] == "vbad"


@pytest.mark.asyncio
async def test_download_emits_complete_with_counts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """complete event aggregates downloaded/failed counts."""
    _patch_subprocess(monkeypatch, [0, 1, 0])
    _patch_minio(monkeypatch, [])
    _patch_filesystem(monkeypatch, tmp_path)
    (tmp_path / "v1.mp3").write_bytes(b"a")
    (tmp_path / "v3.mp3").write_bytes(b"a")

    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)

    from youtube import download

    task = {
        "task_id": "t-3",
        "items": [
            {"id": "v1", "url": "u1"},
            {"id": "v2", "url": "u2"},
            {"id": "v3", "url": "u3"},
        ],
        "output": {"type": "minio", "endpoint": "x", "bucket": "b", "prefix": "p/",
                   "access_key": "k", "secret_key": "s"},
    }
    rc = await download.run(task)
    assert rc == 3  # partial failure

    events = [json.loads(line) for line in buf.getvalue().strip().split("\n")]
    complete = events[-1]
    assert complete == {"type": "complete", "downloaded": 2, "failed": 1}
```

- [ ] **Step 2: Vérifier que le test échoue**

Run: `cd docker/scrapers/youtube && uv run pytest tests/test_download.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'youtube.download'`.

- [ ] **Step 3: Écrire l'implémentation**

`docker/scrapers/youtube/youtube/download.py` :
```python
"""Download command : extract audio of selected items via yt-dlp + upload to MinIO."""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

from youtube import minio_uploader
from youtube.events import emit


def _tmp_dir() -> Path:
    """Return the temp dir used for intermediate audio files (overridable in tests)."""
    return Path(tempfile.gettempdir())


def _build_yt_dlp_cmd(item_url: str, item_id: str, output_path: Path, options: dict[str, Any]) -> list[str]:
    audio_format = options.get("audio_format", "mp3")
    audio_quality = str(options.get("audio_quality", 9))
    audio_args = options.get("audio_args", "-ac 1 -ar 16000 -b:a 32k")
    sleep_min = str(options.get("sleep_interval_min", 3))
    sleep_max = str(options.get("sleep_interval_max", 10))
    return [
        "yt-dlp",
        "-x",
        "--audio-format", audio_format,
        "--audio-quality", audio_quality,
        "--postprocessor-args", f"ffmpeg:{audio_args}",
        "--sleep-interval", sleep_min,
        "--max-sleep-interval", sleep_max,
        "-o", str(output_path),
        item_url,
    ]


async def _download_one(item: dict[str, Any], output_cfg: dict[str, Any], options: dict[str, Any]) -> bool:
    """Download one item, upload, emit events. Returns True on success."""
    item_id = item["id"]
    item_url = item["url"]
    local_path = _tmp_dir() / f"{item_id}.mp3"

    cmd = _build_yt_dlp_cmd(item_url, item_id, local_path, options)

    emit("progress", item_id=item_id, phase="downloading", percent=0)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()

    if proc.returncode != 0 or not local_path.exists():
        emit("item_failed", item_id=item_id, error=f"yt-dlp exited {proc.returncode}")
        return False

    s3_key = minio_uploader.upload_audio(local_path, output_cfg, item_id)
    size = local_path.stat().st_size
    local_path.unlink(missing_ok=True)

    emit(
        "item_done",
        item_id=item_id,
        audio_s3_key=s3_key,
        metadata={"size_bytes": size, "format": output_cfg.get("format", "mp3")},
    )
    return True


async def run(task: dict[str, Any]) -> int:
    """Download every item in task['items']. Returns exit code per spec § Codes de sortie."""
    items = task.get("items", [])
    options = task.get("options", {})
    output_cfg = task["output"]

    downloaded = 0
    failed = 0
    for item in items:
        ok = await _download_one(item, output_cfg, options)
        if ok:
            downloaded += 1
        else:
            failed += 1

    emit("complete", downloaded=downloaded, failed=failed)

    if failed == 0:
        return 0
    if downloaded == 0:
        return 2
    return 3
```

- [ ] **Step 4: Vérifier que les tests passent**

Run: `cd docker/scrapers/youtube && uv run pytest tests/test_download.py -v`

Expected: PASS — 3 tests verts.

- [ ] **Step 5: Commit**

```bash
git add docker/scrapers/youtube/youtube/download.py docker/scrapers/youtube/tests/test_download.py
git commit -m "$(cat <<'EOF'
feat(scrapers): youtube.download (yt-dlp -x mp3 mono 16kHz + upload MinIO + events)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

## Task A6 : Module `minio_uploader.py`

**Files:**
- Create: `docker/scrapers/youtube/youtube/minio_uploader.py`
- Create: `docker/scrapers/youtube/tests/test_minio_uploader.py`

- [ ] **Step 1: Écrire le test qui échoue**

`docker/scrapers/youtube/tests/test_minio_uploader.py` :
```python
"""Tests for the MinIO upload helper inside the scraper container."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


class _StubMinio:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def fput_object(self, bucket: str, key: str, file_path: str, content_type: str = "application/octet-stream") -> None:
        self.calls.append({"bucket": bucket, "key": key, "file_path": file_path, "content_type": content_type})


@pytest.fixture()
def stub_minio(monkeypatch: pytest.MonkeyPatch) -> _StubMinio:
    stub = _StubMinio()
    monkeypatch.setattr("youtube.minio_uploader._build_client", lambda cfg: stub)
    return stub


def test_upload_audio_writes_to_correct_key(tmp_path: Path, stub_minio: _StubMinio) -> None:
    """upload_audio composes prefix + item_id + .mp3."""
    audio = tmp_path / "v1.mp3"
    audio.write_bytes(b"x" * 1024)

    from youtube import minio_uploader

    cfg = {
        "endpoint": "http://minio:9000",
        "bucket": "corpus-audio",
        "prefix": "tenant/role/source/",
        "access_key": "k",
        "secret_key": "s",
    }
    s3_key = minio_uploader.upload_audio(audio, cfg, item_id="v1")

    assert s3_key == "tenant/role/source/v1.mp3"
    assert stub_minio.calls == [{
        "bucket": "corpus-audio",
        "key": "tenant/role/source/v1.mp3",
        "file_path": str(audio),
        "content_type": "audio/mpeg",
    }]


def test_upload_audio_handles_prefix_without_trailing_slash(
    tmp_path: Path, stub_minio: _StubMinio,
) -> None:
    """A prefix without trailing slash still produces a valid key."""
    audio = tmp_path / "v2.mp3"
    audio.write_bytes(b"x")

    from youtube import minio_uploader

    cfg = {"endpoint": "x", "bucket": "b", "prefix": "tenant/role/source",
           "access_key": "k", "secret_key": "s"}
    s3_key = minio_uploader.upload_audio(audio, cfg, item_id="v2")
    assert s3_key == "tenant/role/source/v2.mp3"
```

- [ ] **Step 2: Vérifier que le test échoue**

Run: `cd docker/scrapers/youtube && uv run pytest tests/test_minio_uploader.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'youtube.minio_uploader'`.

- [ ] **Step 3: Écrire l'implémentation**

`docker/scrapers/youtube/youtube/minio_uploader.py` :
```python
"""MinIO upload helper for the YouTube scraper container."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from minio import Minio


def _build_client(cfg: dict[str, Any]) -> Minio:
    """Construct a Minio client from the task's output config."""
    parsed = urlparse(cfg["endpoint"])
    secure = parsed.scheme == "https"
    netloc = parsed.netloc or parsed.path
    return Minio(
        netloc,
        access_key=cfg["access_key"],
        secret_key=cfg["secret_key"],
        secure=secure,
    )


def upload_audio(local_path: Path, cfg: dict[str, Any], item_id: str) -> str:
    """Upload an MP3 audio to MinIO and return its s3_key.

    Key layout : {prefix}{item_id}.mp3 (slash inserted between prefix and item_id if missing).
    """
    client = _build_client(cfg)
    prefix = cfg["prefix"]
    if prefix and not prefix.endswith("/"):
        prefix = prefix + "/"
    key = f"{prefix}{item_id}.mp3"

    client.fput_object(
        cfg["bucket"],
        key,
        str(local_path),
        content_type="audio/mpeg",
    )
    return key
```

- [ ] **Step 4: Vérifier que les tests passent**

Run: `cd docker/scrapers/youtube && uv run pytest tests/test_minio_uploader.py -v`

Expected: PASS — 2 tests verts.

- [ ] **Step 5: Lancer la suite complète + lint**

Run: `cd docker/scrapers/youtube && uv run pytest -v && uv run ruff check youtube/ tests/`

Expected: 8 tests verts (events 2 + discover 3 + download 3 — minio 2 = 10), ruff clean.

> En réalité on a 2 (events) + 3 (discover) + 3 (download) + 2 (minio) = **10 tests**.

- [ ] **Step 6: Commit**

```bash
git add docker/scrapers/youtube/youtube/minio_uploader.py docker/scrapers/youtube/tests/test_minio_uploader.py
git commit -m "$(cat <<'EOF'
feat(scrapers): youtube.minio_uploader (fput_object + content-type audio/mpeg)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

## Task A7 : Script de build local des images scrapers

**Files:**
- Create: `scripts/build_scrapers.sh`

> Ce script build les images localement (sans push registry). Usage : `./scripts/build_scrapers.sh youtube` ou `./scripts/build_scrapers.sh all`. Smoke test manuel possible avec `docker run` une fois l'image construite. Sans Docker installé localement, le script est juste un artefact de référence.

- [ ] **Step 1: Créer `scripts/build_scrapers.sh`**

```bash
#!/usr/bin/env bash
# Build local des images scrapers.
# Usage : ./scripts/build_scrapers.sh [base|youtube|instagram|tiktok|all]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="${1:-all}"

build_base() {
    echo ">> build agflow-scraper-base"
    docker build -t agflow-scraper-base:latest -f "$ROOT/docker/scrapers/base/Dockerfile" "$ROOT/docker/scrapers"
}

build_platform() {
    local platform="$1"
    echo ">> build agflow-scraper-$platform"
    docker build -t "agflow-scraper-$platform:latest" -f "$ROOT/docker/scrapers/$platform/Dockerfile" "$ROOT/docker/scrapers/$platform"
}

case "$TARGET" in
    base) build_base ;;
    youtube|instagram|tiktok)
        build_base
        build_platform "$TARGET"
        ;;
    all)
        build_base
        for p in youtube instagram tiktok; do
            build_platform "$p"
        done
        ;;
    *)
        echo "Unknown target: $TARGET" >&2
        echo "Usage: $0 [base|youtube|instagram|tiktok|all]" >&2
        exit 1
        ;;
esac

echo "Build complete."
```

- [ ] **Step 2: Rendre exécutable**

Run: `chmod +x scripts/build_scrapers.sh`

- [ ] **Step 3: Commit**

```bash
git add scripts/build_scrapers.sh
git commit -m "$(cat <<'EOF'
feat(infra): scripts/build_scrapers.sh (build local des images base + platforms)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Phase B — Containers Instagram et TikTok (squelettes)

Objectif : deux containers minimums qui respectent le contrat stdin/stdout NDJSON sans implémenter le scraping réel. Permet de valider l'orchestrator (Phase C) sur les 3 plateformes même si IG/TT renvoient juste `{"type": "error", "error": "not implemented"}`. Implémentation réelle reportée selon décisions Sprint 2 (yt-dlp pour Instagram, à raffiner Phase 2).

## Task B1 : Container Instagram (stub contractuel)

**Files:**
- Create: `docker/scrapers/instagram/Dockerfile`
- Create: `docker/scrapers/instagram/instagram/__init__.py`
- Create: `docker/scrapers/instagram/instagram/entrypoint.py`

- [ ] **Step 1: Créer `docker/scrapers/instagram/instagram/__init__.py`**

```python
"""Instagram scraper package (stub Sprint 2 — implémentation Phase 2)."""
```

- [ ] **Step 2: Créer `docker/scrapers/instagram/instagram/entrypoint.py`**

```python
"""Instagram scraper entrypoint (stub).

Respecte le contrat stdin JSON / stdout NDJSON pour permettre à l'orchestrator
de tester le pipeline. Renvoie une erreur 'not_implemented' contrôlée plutôt
que de planter.
"""
from __future__ import annotations

import asyncio
import json
import sys


async def main() -> int:
    task_json = sys.stdin.read()
    try:
        task = json.loads(task_json)
    except json.JSONDecodeError as exc:
        print(json.dumps({"type": "error", "error": f"invalid JSON: {exc}"}), flush=True)
        return 1

    print(json.dumps({"type": "started", "task_id": task.get("task_id", "unknown")}), flush=True)
    print(json.dumps({
        "type": "error",
        "error": "instagram scraper not implemented (Sprint 2 stub) — yt-dlp Instagram à câbler Phase 2",
    }), flush=True)
    return 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

- [ ] **Step 3: Créer `docker/scrapers/instagram/Dockerfile`**

```dockerfile
FROM agflow-scraper-base:latest

COPY instagram/ /app/instagram/

ENTRYPOINT ["python", "-m", "instagram.entrypoint"]
```

- [ ] **Step 4: Commit**

```bash
git add docker/scrapers/instagram/
git commit -m "$(cat <<'EOF'
chore(scrapers): instagram stub contractuel (NDJSON 'started' + 'error' not_implemented)

Câblage yt-dlp Instagram reporté Phase 2 (cf. 12-open-decisions § Scrapers).
Le contrat stdin/stdout est respecté pour permettre les tests d'orchestration.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

## Task B2 : Container TikTok (stub contractuel)

**Files:**
- Create: `docker/scrapers/tiktok/Dockerfile`
- Create: `docker/scrapers/tiktok/tiktok/__init__.py`
- Create: `docker/scrapers/tiktok/tiktok/entrypoint.py`

- [ ] **Step 1: Créer `docker/scrapers/tiktok/tiktok/__init__.py`**

```python
"""TikTok scraper package (stub Sprint 2 — implémentation Phase 2)."""
```

- [ ] **Step 2: Créer `docker/scrapers/tiktok/tiktok/entrypoint.py`**

```python
"""TikTok scraper entrypoint (stub). Voir instagram/entrypoint.py pour la rationale."""
from __future__ import annotations

import asyncio
import json
import sys


async def main() -> int:
    task_json = sys.stdin.read()
    try:
        task = json.loads(task_json)
    except json.JSONDecodeError as exc:
        print(json.dumps({"type": "error", "error": f"invalid JSON: {exc}"}), flush=True)
        return 1

    print(json.dumps({"type": "started", "task_id": task.get("task_id", "unknown")}), flush=True)
    print(json.dumps({
        "type": "error",
        "error": "tiktok scraper not implemented (Sprint 2 stub) — câblage Phase 2",
    }), flush=True)
    return 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

- [ ] **Step 3: Créer `docker/scrapers/tiktok/Dockerfile`**

```dockerfile
FROM agflow-scraper-base:latest

COPY tiktok/ /app/tiktok/

ENTRYPOINT ["python", "-m", "tiktok.entrypoint"]
```

- [ ] **Step 4: Commit**

```bash
git add docker/scrapers/tiktok/
git commit -m "$(cat <<'EOF'
chore(scrapers): tiktok stub contractuel (NDJSON 'started' + 'error' not_implemented)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## ⚠️ CHECKPOINT — Fin Phase B / avant Phase C

À ce point, les 3 images scrapers sont prêtes (YouTube fonctionnel + IG/TT stubs contractuels), 10 tests Python verts pour le code YouTube, le script `build_scrapers.sh` permet de construire les images localement. **Aucun code backend n'a été touché**. Prochaine étape : Phase C (orchestrator backend qui instancie les containers Docker depuis FastAPI).

**Décisions à confirmer avant Phase C** :

1. **Stratégie credentials sans OpenBao** :
   - Option A (retenue par défaut) : env var optionnelle `YOUTUBE_COOKIES_B64` lue depuis `.env` du backend → passée au container. Pas de creds en base, pas de fetch OpenBao. Tests possibles uniquement sur contenus publics (qui marchent sans cookies).
   - Option B : ne pas lire de creds du tout dans Sprint 2, l'orchestrator ne passe que `URL` au container. Plus simple, équivalent fonctionnellement.
   - Option C : implémenter OpenBao quand même (détourne du chemin "OpenBao à la fin").

2. **Taille de la Phase C** : ~600 lignes de code backend (db_helpers + docker_runner + scraper_orchestrator + event_handlers). Souhaite-t-on faire Phase C d'une traite, ou la découper en sous-checkpoints (db_helpers d'abord, puis docker_runner, puis orchestrator) ?

3. **Lancement réel des containers** : sans Docker installé localement, l'orchestrator est testé uniquement via mock subprocess. Le test runtime nécessite Docker Desktop ou exécution sur LXC pve1.

---

# Phase C — Backend orchestrator (à détailler après checkpoint)

Périmètre prévu (les détails de code seront ajoutés au plan après confirmation utilisateur) :

- **C1** : `backend/src/role_builder/db_helpers/{sources,source_items,scraping_jobs,credentials}.py`
  - Fonctions `insert_*`, `update_*`, `claim_next_job` (`FOR UPDATE SKIP LOCKED`), `get_*`, `list_*`. TDD pur (asyncpg mocké via fixtures).
- **C2** : `backend/src/role_builder/services/docker_runner.py`
  - Wrapper `run_container(image, env, stdin_payload) -> AsyncIterator[dict]` qui lance `docker run --rm -i image` via `asyncio.create_subprocess_exec`, écrit le JSON stdin, parse les events NDJSON ligne par ligne en streaming. TDD avec subprocess mocké.
- **C3** : `backend/src/role_builder/services/scraper_orchestrator.py`
  - Boucle `pull_and_run` : pull `scraping_jobs`, choisit l'image selon `source.platform`, construit le payload de tâche, appelle `docker_runner.run_container`, dispatch events vers `event_handlers`. Cap simultané `MAX_CONCURRENT_SCRAPERS`.
- **C4** : `backend/src/role_builder/services/event_handlers.py`
  - Handler par type d'event (`discovered`, `item_done`, `item_failed`, `complete`, `error`). Chaque handler met à jour `source_items` ou `scraping_jobs` via les db_helpers.
- **C5** : `backend/src/role_builder/main.py` modifié pour démarrer la boucle orchestrator dans `lifespan` + variable `MAX_CONCURRENT_SCRAPERS` dans `config.py`.

# Phase D — WebSocket relay (à détailler après Phase C)

- **D1** : `backend/src/role_builder/services/ws_relay.py` — connexion asyncpg dédiée + `add_listener` sur les 4 channels (`source_items_changes`, `runs_changes`, `workers_changes`, `keys_changes`).
- **D2** : `backend/src/role_builder/routes/websocket.py` — endpoint FastAPI `/ws`, filter par `tenant_id`, broadcast aux clients connectés. Test avec `TestClient.websocket_connect`.

# Phase E — API REST sources/items

- **E1** : `backend/src/role_builder/schemas/{sources,items}.py` — DTOs Pydantic (cf. spec 03 § Schemas Pydantic).
- **E2** : `backend/src/role_builder/routes/sources.py` — `POST /role-projects/{id}/sources`, `POST /sources/{id}/discover`, `GET /sources/{id}/items` (avec filtres `min_duration_s`, `since_date`, `status`, `selected`, `limit`/`offset`), `POST /sources/{id}/items/select`.
- **E3** : `backend/src/role_builder/routes/scraping_jobs.py` — `GET /scraping-jobs` (suivi).

# Phase F — Frontend onglet Sources

- **F1** : Ajouter SWR à `frontend/package.json` + `npm install`.
- **F2** : `frontend/src/lib/api/{sources,items}.ts` + `frontend/src/lib/types.ts`.
- **F3** : `frontend/src/lib/ws/{connection,hooks}.ts` (WSManager singleton, hook `useWebSocketEvent`).
- **F4** : `frontend/src/app/projects/[id]/sources/page.tsx` (liste sources, bouton "Ajouter").
- **F5** : `frontend/src/app/projects/[id]/sources/[sourceId]/page.tsx` + `DiscoverButton`, `ItemsTable`, `ItemsFilters`, `SelectionActions`. Live updates via `useWebSocketEvent('source_items_changes')`.

# Phase G — Vérification end-to-end + tag

- **G1** : `pytest -v` (backend) + `npm test` (frontend) + lint + typecheck → tout vert.
- **G2** : Smoke test manuel — `./scripts/build_scrapers.sh youtube`, lancer la stack docker compose, créer un projet via UI, ajouter une URL de chaîne YouTube publique (ex: chaîne d'archives publiques YouTube), lancer discover, sélectionner 2-3 vidéos courtes, vérifier que les MP3 atterrissent dans MinIO.
- **G3** : Tag `v0.2.0-sprint-2`.
- **G4** : MAJ `docs/specs/12-open-decisions.md` avec les décisions Sprint 2 actées.

---

## Récapitulatif provisoire des commits

À ce stade du plan (Phases A + B), les commits attendus sont :

1. `chore(scrapers): image base ...` (A1)
2. `chore(scrapers): squelette package youtube ...` (A2)
3. `feat(scrapers): emitter NDJSON events youtube ...` (A3)
4. `feat(scrapers): youtube.discover ...` (A4)
5. `feat(scrapers): youtube.download ...` (A5)
6. `feat(scrapers): youtube.minio_uploader ...` (A6)
7. `feat(infra): scripts/build_scrapers.sh ...` (A7)
8. `chore(scrapers): instagram stub contractuel ...` (B1)
9. `chore(scrapers): tiktok stub contractuel ...` (B2)

= 9 commits (Phases A+B). Les commits Phases C-G seront définis après checkpoint.

Tag final visé : `v0.2.0-sprint-2`. Estimation totale Sprint 2 : ~30-40 commits selon décisions checkpoint.

---

**Status du plan** : Phases A et B complètement détaillées (TDD, code complet, commits prescrits). Phases C à G en haut niveau, à détailler après le checkpoint utilisateur de fin de Phase B. Cette structure permet de démarrer l'exécution immédiatement sur les containers tout en sécurisant la décision sur l'orchestrator backend.
