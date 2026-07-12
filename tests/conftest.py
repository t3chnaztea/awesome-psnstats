"""Shared test fixtures and builders. All tests run with zero network."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from psnstats.analysis import Game

# Fixed clock so recency/enjoyment are deterministic.
NOW = datetime(2026, 7, 12, 12, 0, 0)


def make_game(
    title="Game",
    title_id="CUSA00001_00",
    system="PS4",
    playtime_hours=10.0,
    play_count=1,
    last_played=NOW,
    completion_progress=None,
) -> Game:
    return Game(
        title=title,
        title_id=title_id,
        system=system,
        playtime_hours=playtime_hours,
        play_count=play_count,
        last_played=last_played,
        completion_progress=completion_progress,
    )


@pytest.fixture
def now():
    return NOW


@pytest.fixture
def days_ago():
    def _days_ago(n):
        return NOW - timedelta(days=n)

    return _days_ago
