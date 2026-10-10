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
from mcp.server.transport_security import TransportSecuritySettings

from role_builder.mcp_server.tools import admin, corpus, discovery, status, submission

# streamable_http_path="/" : monté sur /mcp (main.py), l'endpoint réel est
# alors /mcp — sans ça FastMCP ajoute son propre /mcp et le tout serait servi
# sur /mcp/mcp (BUG-03).
#
# transport_security : la protection DNS-rebinding par défaut (host localhost)
# rejette 421 toute requête dont le Host n'est pas localhost — donc 100 % des
# appels de la passerelle en déploiement. On la désactive : la façade est
# derrière la passerelle (réseau privé) et protégée par MCPAuthMiddleware
# (BUG-04).
mcp = FastMCP(
    "roles",
    streamable_http_path="/",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)

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
