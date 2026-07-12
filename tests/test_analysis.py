"""Tests for the pure taste-analysis engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from conftest import NOW, make_game
from psnstats.analysis import (
    analyze_preferences,
    compute_entropy,
    compute_per_game_features,
    percentile_scale,
)


def test_enjoyment_regression_pin(now):
    """Lock a hand-computed enjoyment score so refactors can't drift the model.

    100h, 10 plays, played today, no completion data:
      playtime_log = ln(101)/ln(200)*100 = 87.106 ; *0.35 = 30.487
      recency      = 100                            ; *0.25 = 25.0
      completion   = 50 (neutral, no data)          ; *0.20 = 10.0
      replay       = 100 (capped)                   ; *0.20 = 20.0
      total = 85.487 -> 85.5
    """
    feat = compute_per_game_features(
        make_game(playtime_hours=100.0, play_count=10, last_played=now), now
    )
    assert feat["enjoyment_score"] == 85.5
    assert feat["recency_days"] == 0
    assert feat["recency_score"] == 1.0


def test_empty_library_raises(now):
    with pytest.raises(ValueError):
        analyze_preferences([], now=now)


def test_single_game_bounds(now):
    pkg = analyze_preferences([make_game()], now=now)
    for trait in pkg["preferences"]["traits"].values():
        assert 5 <= trait["value"] <= 95
    assert pkg["preferences"]["summary"]["game_count"] == 1


def test_no_completion_data_is_neutral(now):
    games = [make_game(title=f"G{i}", title_id=f"CUSA{i:05d}_00", playtime_hours=5.0) for i in range(4)]
    pkg = analyze_preferences(games, now=now)
    assert pkg["preferences"]["traits"]["completionist_bias"]["value"] == 50
    assert pkg["preferences"]["agent_features"]["preferred_commitment_style"] == "mixed"


def test_friction_tolerance_no_abandon(now):
    # No completion data -> no abandon flags -> friction at ceiling.
    games = [make_game(title=f"G{i}", title_id=f"CUSA{i:05d}_00") for i in range(5)]
    pkg = analyze_preferences(games, now=now)
    assert pkg["preferences"]["traits"]["friction_tolerance"]["value"] == 95.0


def test_friction_tolerance_with_one_abandon(now):
    # 1 early-abandon out of 4 -> rate 0.25 -> 95 - 0.25*180 = 50.0
    good = [
        make_game(title=f"G{i}", title_id=f"CUSA{i:05d}_00", playtime_hours=5.0, completion_progress=90)
        for i in range(3)
    ]
    bad = make_game(
        title="Abandoned", title_id="CUSA99999_00", playtime_hours=2.0, play_count=3, completion_progress=10
    )
    pkg = analyze_preferences([*good, bad], now=now)
    assert pkg["preferences"]["traits"]["friction_tolerance"]["value"] == 50.0


def test_variety_single_system_is_floor(now):
    games = [make_game(title=f"G{i}", title_id=f"CUSA{i:05d}_00", system="PS4") for i in range(4)]
    pkg = analyze_preferences(games, now=now)
    assert pkg["preferences"]["traits"]["variety_bias"]["value"] == 5.0


def test_variety_two_balanced_systems_is_ceiling(now):
    games = [
        make_game(title="A", title_id="CUSA00001_00", system="PS4"),
        make_game(title="B", title_id="CUSA00002_00", system="PS4"),
        make_game(title="C", title_id="PPSA00001_00", system="PS5"),
        make_game(title="D", title_id="PPSA00002_00", system="PS5"),
    ]
    pkg = analyze_preferences(games, now=now)
    assert pkg["preferences"]["traits"]["variety_bias"]["value"] == 95.0


def test_abandonment_flags(now):
    early = compute_per_game_features(
        make_game(playtime_hours=2.0, play_count=3, completion_progress=10), now
    )
    assert early["abandonment_flags"] == {"early_abandon": True, "late_abandon": False}

    late = compute_per_game_features(
        make_game(playtime_hours=15.0, play_count=1, completion_progress=30), now
    )
    assert late["abandonment_flags"] == {"early_abandon": False, "late_abandon": True}

    healthy = compute_per_game_features(
        make_game(playtime_hours=5.0, play_count=1, completion_progress=80), now
    )
    assert healthy["abandonment_flags"] == {"early_abandon": False, "late_abandon": False}


def test_completion_ratio_only_with_trophy_data(now):
    without = compute_per_game_features(make_game(completion_progress=None), now)
    assert without["completion_ratio"] is None
    with_data = compute_per_game_features(make_game(completion_progress=75), now)
    assert with_data["completion_ratio"] == 0.75


def test_platform_recency_sums_to_100(now):
    games = [
        make_game(title="A", title_id="CUSA00001_00", system="PS4", playtime_hours=20.0),
        make_game(title="B", title_id="PPSA00001_00", system="PS5", playtime_hours=40.0),
    ]
    pkg = analyze_preferences(games, now=now)
    pr = pkg["preferences"]["agent_features"]["platform_recency"]
    assert round(pr["PS5"] + pr["PS4"], 1) == 100.0
    assert pr["PS5"] > pr["PS4"]  # PS5 has more (recency-weighted) playtime


def test_all_traits_and_scores_bounded(now):
    games = [
        make_game(title=f"G{i}", title_id=f"CUSA{i:05d}_00", playtime_hours=float(i + 1),
                  play_count=i + 1, completion_progress=(i * 13) % 100)
        for i in range(12)
    ]
    pkg = analyze_preferences(games, now=now)
    for trait in pkg["preferences"]["traits"].values():
        assert 5 <= trait["value"] <= 95
    for feat in pkg["per_game_features"]:
        assert 0 <= feat["enjoyment_score"] <= 100


def test_helpers():
    assert percentile_scale([], 5) == 50.0
    assert percentile_scale([1.0], 1.0) == 50.0
    assert compute_entropy([5]) == 0.0
    assert compute_entropy([1, 1]) == pytest.approx(1.0)


def test_full_timestamp_recency_not_month_truncated(days_ago):
    """Port fix 4: recency uses the full timestamp, not YYYY-01 truncation."""
    feat = compute_per_game_features(make_game(last_played=days_ago(10)), NOW)
    assert feat["recency_days"] == 10


def test_tz_aware_last_played_does_not_crash():
    """psnawp returns aware datetimes; a naive analysis clock must still work."""
    aware = datetime(2026, 7, 2, 12, 0, 0, tzinfo=timezone.utc)
    feat = compute_per_game_features(make_game(last_played=aware), NOW)  # NOW is naive
    assert feat["recency_days"] == 10

    # And the full pipeline with the aware timestamp + default (naive) clock.
    game = make_game(last_played=datetime.now(timezone.utc) - timedelta(days=5))
    pkg = analyze_preferences([game])
    assert pkg["preferences"]["summary"]["game_count"] == 1
