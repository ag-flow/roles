"""Tests for services.acquisition.status_shape — fold_counts + derive_display_status (pure)."""

from __future__ import annotations

from role_builder.services.acquisition.status_shape import derive_display_status, fold_counts


def test_fold_counts_aggregates_pipeline_stages() -> None:
    rows = [
        {"status": "pending_download", "selected": True, "n": 3},
        {"status": "pending_download", "selected": False, "n": 5},
        {"status": "audio_ready", "selected": True, "n": 2},
        {"status": "transcribed", "selected": True, "n": 4},
        {"status": "deposited", "selected": True, "n": 1},
        {"status": "failed", "selected": True, "n": 2},
    ]

    counts = fold_counts(rows)

    assert counts["discovered"] == 17
    assert counts["selected"] == 12  # 3+2+4+1+2
    assert counts["pending"] == 3  # pending_download AND selected
    assert counts["downloaded"] == 7  # audio_ready + transcribed + deposited
    assert counts["transcribed"] == 5  # transcribed + deposited
    assert counts["deposited"] == 1
    assert counts["failed"] == 2


def test_fold_counts_empty_rows() -> None:
    counts = fold_counts([])
    assert counts == {
        "discovered": 0,
        "selected": 0,
        "pending": 0,
        "downloaded": 0,
        "transcribed": 0,
        "deposited": 0,
        "failed": 0,
    }


def test_derive_display_status_keeps_discovery_stages_verbatim() -> None:
    counts = fold_counts([])
    assert derive_display_status("discovering", counts, selected_total=0) == "discovering"
    assert derive_display_status("discovered", counts, selected_total=0) == "discovered"


def test_derive_display_status_keeps_cancelled() -> None:
    counts = fold_counts([])
    assert derive_display_status("cancelled", counts, selected_total=5) == "cancelled"


def test_derive_display_status_acquiring_while_items_in_flight() -> None:
    counts = fold_counts(
        [
            {"status": "pending_download", "selected": True, "n": 2},
            {"status": "deposited", "selected": True, "n": 1},
        ]
    )
    assert derive_display_status("acquiring", counts, selected_total=3) == "acquiring"


def test_derive_display_status_completed_when_all_deposited() -> None:
    counts = fold_counts([{"status": "deposited", "selected": True, "n": 3}])
    assert derive_display_status("acquiring", counts, selected_total=3) == "completed"


def test_derive_display_status_partially_failed_when_some_failed() -> None:
    counts = fold_counts(
        [
            {"status": "deposited", "selected": True, "n": 2},
            {"status": "failed", "selected": True, "n": 1},
        ]
    )
    assert derive_display_status("acquiring", counts, selected_total=3) == "partially_failed"
