"""Tests for services.acquisition.filters — résolution des filtres déclaratifs (§2.1)."""

from __future__ import annotations

from datetime import UTC, datetime

from role_builder.services.acquisition.filters import resolve_item_filters


def test_resolve_item_filters_empty_dict_means_match_all() -> None:
    assert resolve_item_filters({}) == {}


def test_resolve_item_filters_none_means_match_all() -> None:
    assert resolve_item_filters(None) == {}


def test_resolve_item_filters_maps_duration_and_title() -> None:
    resolved = resolve_item_filters(
        {"min_duration_s": 60, "max_duration_s": 1800, "title_contains": "UX"}
    )
    assert resolved == {
        "min_duration_s": 60,
        "max_duration_s": 1800,
        "title_contains": "UX",
    }


def test_resolve_item_filters_parses_since_until_as_dates() -> None:
    resolved = resolve_item_filters({"since": "2026-01-01", "until": "2026-06-30"})
    assert resolved["since_date"] == datetime(2026, 1, 1, tzinfo=UTC)
    assert resolved["until_date"] == datetime(2026, 6, 30, tzinfo=UTC)


def test_resolve_item_filters_max_items_becomes_limit() -> None:
    resolved = resolve_item_filters({"max_items": 25})
    assert resolved["limit"] == 25
    assert "max_items" not in resolved
