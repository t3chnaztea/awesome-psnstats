"""Tests for the compare (delta) math."""

from __future__ import annotations

from psnstats.compare import compare_packages, render_compare


def _pkg(features, traits):
    return {
        "per_game_features": features,
        "preferences": {"traits": {k: {"value": v} for k, v in traits.items()}},
    }


def test_compare_new_titles_and_hours_gained():
    old = _pkg(
        [{"title_id": "A", "title": "Alpha", "system": "PS4", "playtime_hours": 10.0}],
        {"snackable_bias": 40.0, "marathon_bias": 55.0},
    )
    new = _pkg(
        [
            {"title_id": "A", "title": "Alpha", "system": "PS4", "playtime_hours": 15.0},
            {"title_id": "B", "title": "Beta", "system": "PS5", "playtime_hours": 5.0},
        ],
        {"snackable_bias": 48.0, "marathon_bias": 55.0},
    )
    delta = compare_packages(old, new)

    assert [t["title"] for t in delta["new_titles"]] == ["Beta"]
    assert delta["removed_count"] == 0
    # Alpha +5, Beta +5 (new) -> total 10.0
    assert delta["total_hours_gained"] == 10.0
    gained = {g["title"]: g["hours_gained"] for g in delta["hours_gained"]}
    assert gained == {"Alpha": 5.0, "Beta": 5.0}


def test_compare_trait_drift_threshold():
    old = _pkg([], {"snackable_bias": 40.0, "marathon_bias": 55.0})
    new = _pkg([], {"snackable_bias": 48.0, "marathon_bias": 56.0})
    drift = compare_packages(old, new)["trait_drift"]
    assert drift["snackable_bias"]["delta"] == 8.0
    assert drift["snackable_bias"]["moved"] is True
    assert drift["marathon_bias"]["delta"] == 1.0
    assert drift["marathon_bias"]["moved"] is False


def test_compare_removed_titles():
    old = _pkg(
        [
            {"title_id": "A", "title": "Alpha", "system": "PS4", "playtime_hours": 10.0},
            {"title_id": "B", "title": "Beta", "system": "PS5", "playtime_hours": 5.0},
        ],
        {},
    )
    new = _pkg(
        [{"title_id": "A", "title": "Alpha", "system": "PS4", "playtime_hours": 10.0}], {}
    )
    delta = compare_packages(old, new)
    assert delta["removed_count"] == 1
    assert delta["new_titles"] == []


def test_render_compare_smoke():
    old = _pkg(
        [{"title_id": "A", "title": "Alpha", "system": "PS4", "playtime_hours": 10.0}],
        {"snackable_bias": 40.0},
    )
    new = _pkg(
        [
            {"title_id": "A", "title": "Alpha", "system": "PS4", "playtime_hours": 20.0},
            {"title_id": "B", "title": "Beta", "system": "PS5", "playtime_hours": 8.0},
        ],
        {"snackable_bias": 60.0},
    )
    out = render_compare(compare_packages(old, new))
    assert "COMPARE" in out
    assert "Beta" in out
    assert "Trait drift" in out
