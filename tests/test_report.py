"""Tests for the ASCII / markdown report renderers."""

from __future__ import annotations

from conftest import make_game
from psnstats.analysis import analyze_preferences
from psnstats.report import (
    render_ascii_bar,
    render_ascii_report,
    render_markdown_report,
)


def _package(now):
    games = [
        make_game(title="Bloodborne", title_id="CUSA00900_00", system="PS4",
                  playtime_hours=42.0, play_count=7, completion_progress=88),
        make_game(title="Returnal", title_id="PPSA01512_00", system="PS5",
                  playtime_hours=30.0, play_count=12, completion_progress=64),
    ]
    return analyze_preferences(games, now=now)


def test_ascii_bar():
    assert render_ascii_bar(0) == "[" + "-" * 20 + "]"
    assert render_ascii_bar(100) == "[" + "#" * 20 + "]"
    assert render_ascii_bar(50) == "[" + "#" * 10 + "-" * 10 + "]"
    assert render_ascii_bar(150) == "[" + "#" * 20 + "]"  # clamped


def test_ascii_report_is_deterministic(now):
    pkg = _package(now)
    stats = {"total_fetched": 5, "included": 2, "skipped_platform": 1, "skipped_playtime": 2}
    first = render_ascii_report(pkg, stats)
    second = render_ascii_report(pkg, stats)
    assert first == second


def test_ascii_report_structure(now):
    pkg = _package(now)
    stats = {"total_fetched": 5, "included": 2, "skipped_platform": 1, "skipped_playtime": 2}
    out = render_ascii_report(pkg, stats, top=10, sort="enjoyment")
    assert "ANALYSIS REPORT" in out
    assert "PLAYER TRAITS" in out
    assert "PLAY STYLE" in out
    assert "SIGNALS" in out
    assert "Bloodborne" in out
    assert "Completionist" in out


def test_ascii_report_sort_hours_orders_by_playtime(now):
    pkg = _package(now)
    stats = {"total_fetched": 2, "included": 2, "skipped_platform": 0, "skipped_playtime": 0}
    out = render_ascii_report(pkg, stats, top=2, sort="hours")
    body = out.split("TOP 2 GAMES")[1]
    # Bloodborne (42h) appears before Returnal (30h).
    assert body.index("Bloodborne") < body.index("Returnal")


def test_markdown_report(now):
    pkg = _package(now)
    md = render_markdown_report(pkg, top=5, sort="enjoyment")
    assert md.startswith("# PlayStation Taste Profile")
    assert "## Player traits" in md
    assert "**Bloodborne**" in md
    assert md.endswith("\n")
