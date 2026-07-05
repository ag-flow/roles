"""Construit le serveur MCP `roles` et enregistre les tools `roles__*`.

Un seul processus : le serveur MCP est monté comme sous-application ASGI
dans l'app FastAPI (cf. main.py), pas de process séparé. Double posture
MCP (backend + client docflow, cf. fondations §3) — ce module ne couvre
que la posture backend (les tools exposés), la posture client (dépôt
docflow) arrive au lot suivant.

Tools enregistrés sous leur nom `roles__*` littéral (§2) plutôt que de
compter sur un préfixage côté passerelle — la façade reste correcte quelle
que soit la politique de nommage du gateway.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from role_builder.mcp_server.tools import admin, corpus, discovery, status, submission, upload

mcp = FastMCP("roles")

mcp.add_tool(
    submission.submit_acquisition,
    name="roles__submit_acquisition",
    description="Soumet une acquisition (chaîne, playlist, compte ou vidéo unique).",
)
mcp.add_tool(
    discovery.list_discovered,
    name="roles__list_discovered",
    description="Liste enrichie des items découverts (titre, extrait, tags, durée).",
)
mcp.add_tool(
    discovery.select_items,
    name="roles__select_items",
    description="Sélectionne les items à télécharger/transcrire (idempotent, cumulable).",
)
mcp.add_tool(
    upload.create_upload_request,
    name="roles__create_upload_request",
    description="Ouvre une requête d'acquisition de type upload (médias hors plateformes).",
)
mcp.add_tool(
    upload.request_upload_slot,
    name="roles__request_upload_slot",
    description=(
        "Crée un item et un slot d'upload : URL présignée PUT MinIO (TTL 1 h), "
        "liste blanche media_type ; le fichier ne transite jamais par MCP."
    ),
)
mcp.add_tool(
    upload.finalize_upload,
    name="roles__finalize_upload",
    description=(
        "Après le PUT : vérifie l'objet MinIO, extrait l'audio si vidéo, et met "
        "l'item en pipeline standard (transcription → dépôt docflow)."
    ),
)
mcp.add_tool(
    upload.close_upload_request,
    name="roles__close_upload_request",
    description="Ferme l'intake (plus de nouveaux slots) ; la complétion suit les items en cours.",
)
mcp.add_tool(
    status.request_status,
    name="roles__request_status",
    description="Statut détaillé d'une requête : counts, items résumés, coût, queue_position.",
)
mcp.add_tool(
    status.list_requests,
    name="roles__list_requests",
    description="Reprise conversationnelle et vue multi-acteurs des requêtes.",
)
mcp.add_tool(
    corpus.get_corpus,
    name="roles__get_corpus",
    description=(
        "Références docflow des transcripts déjà déposés (jamais de contenu) ; "
        "only_new avec curseur par appelant."
    ),
)
mcp.add_tool(
    admin.cancel_request,
    name="roles__cancel_request",
    description="Annule les jobs pending/claimed ; les items déposés restent dans docflow.",
)
mcp.add_tool(
    admin.retry_failed,
    name="roles__retry_failed",
    description="Re-queue les items failed (tous, ou une sélection).",
)
