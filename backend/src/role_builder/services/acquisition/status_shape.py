"""Calcul pur des `counts` et du statut affiché de roles__request_status (§2.3).

Séparé de status.py (qui touche la DB) pour rester testable sans pool.
"""

from __future__ import annotations

from typing import Any

_DOWNLOADED_STATUSES = {"audio_ready", "queued_transcription", "transcribing", "transcribed",
                        "depositing", "deposited"}
_TRANSCRIBED_STATUSES = {"transcribed", "depositing", "deposited"}
_PENDING_STATUSES = {"pending_download", "downloading", "awaiting_upload",
                     "pending_extraction", "extracting_audio"}

_DISCOVERY_STAGES = {"discovering", "discovered", "open_for_upload"}


def fold_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Replie les lignes de `source_items.count_by_status` en `counts` (§2.3).

    Chaque row : ``{status, selected, n}``.
    """
    counts = {
        "discovered": 0,
        "selected": 0,
        "pending": 0,
        "downloaded": 0,
        "transcribed": 0,
        "deposited": 0,
        "failed": 0,
    }
    for row in rows:
        status, selected, n = row["status"], row["selected"], row["n"]
        counts["discovered"] += n
        if selected:
            counts["selected"] += n
            if status in _PENDING_STATUSES:
                counts["pending"] += n
        if status in _DOWNLOADED_STATUSES:
            counts["downloaded"] += n
        if status in _TRANSCRIBED_STATUSES:
            counts["transcribed"] += n
        if status == "deposited":
            counts["deposited"] += n
        if status == "failed":
            counts["failed"] += n
    return counts


def derive_display_status(stored_status: str, counts: dict[str, int], *, selected_total: int) -> str:
    """Dérive le statut exposé : les stades précoces sont stockés tels quels,
    `completed`/`partially_failed` sont recalculés à la lecture (dépendent
    de l'état courant des items, jamais figés en base).
    """
    if stored_status in ("cancelled", "failed") or stored_status in _DISCOVERY_STAGES:
        return stored_status

    # Requête entrée en acquisition mais 0 item sélectionné (mode=auto sans
    # match, ou upload fermé sans slot) : corpus vide mais terminé — sinon le
    # ticket resterait `acquiring` à jamais et le pilote pull sans fin (BUG-14).
    if selected_total == 0:
        return "completed"

    finished = counts["deposited"] + counts["failed"]
    if finished >= selected_total:
        return "partially_failed" if counts["failed"] > 0 else "completed"
    return "acquiring"
