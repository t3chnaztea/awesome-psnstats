"""Tests for the psnawp layer, using stand-ins for TitleStats/TrophyTitle (no network)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from psnawp_api.models.title_stats import PlatformCategory

from psnstats.fetch import (
    enrich_trophies,
    fetch_title_stats,
    normalize_title_stat,
    platform_label,
)

NOW = datetime(2026, 7, 12, 12, 0, 0)


@dataclass
class FakeStat:
    """Stand-in for psnawp TitleStats."""

    name: str
    title_id: str
    category: object
    play_count: int = 1
    last_played_date_time: datetime | None = NOW
    play_duration: timedelta | None = timedelta(hours=10)


@dataclass
class FakeTrophy:
    """Stand-in for psnawp TrophyTitle."""

    np_title_id: str
    progress: int


class FakeSource:
    def __init__(self, stats, trophies=None):
        self._stats = stats
        self._trophies = trophies or {}

    def title_stats(self, page_size=100):
        return iter(self._stats)

    def trophy_titles_for_title(self, title_ids):
        return [self._trophies[t] for t in title_ids if t in self._trophies]


def test_platform_label():
    assert platform_label(PlatformCategory.PS4) == "PS4"
    assert platform_label(PlatformCategory.PS5) == "PS5"
    assert platform_label(PlatformCategory.UNKNOWN) == "OTHER"
    assert platform_label(None) == "OTHER"


def test_normalize_playtime_is_float():
    stat = FakeStat("Bloodborne", "CUSA00900_00", PlatformCategory.PS4,
                    play_duration=timedelta(hours=1, minutes=30))
    game = normalize_title_stat(stat)
    assert game.system == "PS4"
    assert game.playtime_hours == 1.5  # float, not int-rounded to 2
    assert game.last_played == NOW


def test_normalize_missing_duration():
    stat = FakeStat("Demo", "CUSA1_00", PlatformCategory.PS5, play_duration=None)
    assert normalize_title_stat(stat).playtime_hours == 0.0


def test_fetch_filters_platform_and_playtime_and_sorts():
    stats = [
        FakeStat("Big PS5", "PPSA1_00", PlatformCategory.PS5, play_duration=timedelta(hours=50)),
        FakeStat("Small PS4", "CUSA2_00", PlatformCategory.PS4, play_duration=timedelta(minutes=20)),
        FakeStat("Mid PS4", "CUSA3_00", PlatformCategory.PS4, play_duration=timedelta(hours=5)),
        FakeStat("Other", "XXXX4_00", PlatformCategory.UNKNOWN, play_duration=timedelta(hours=99)),
    ]
    games, fetch_stats = fetch_title_stats(FakeSource(stats), ["ps4", "ps5"], min_hours=1.0)
    titles = [g.title for g in games]
    assert titles == ["Big PS5", "Mid PS4"]  # sorted desc by playtime, filtered
    assert fetch_stats == {
        "total_fetched": 4,
        "skipped_platform": 1,
        "skipped_playtime": 1,
        "included": 2,
    }


def test_fetch_platform_other_opt_in():
    stats = [FakeStat("Other", "XXXX_00", PlatformCategory.UNKNOWN, play_duration=timedelta(hours=3))]
    games, _ = fetch_title_stats(FakeSource(stats), ["other"], min_hours=1.0)
    assert [g.system for g in games] == ["OTHER"]


def test_fetch_limit():
    stats = [
        FakeStat(f"G{i}", f"CUSA{i}_00", PlatformCategory.PS4, play_duration=timedelta(hours=i + 1))
        for i in range(10)
    ]
    games, _ = fetch_title_stats(FakeSource(stats), ["ps4"], min_hours=1.0, limit=3)
    assert len(games) == 3


def test_min_hours_zero_keeps_everything():
    stats = [FakeStat("Tiny", "CUSA_00", PlatformCategory.PS4, play_duration=timedelta(minutes=5))]
    games, _ = fetch_title_stats(FakeSource(stats), ["ps4"], min_hours=0.0)
    assert len(games) == 1


def test_enrich_trophies_maps_by_np_title_id():
    stats = [
        FakeStat("A", "CUSA1_00", PlatformCategory.PS4, play_duration=timedelta(hours=10)),
        FakeStat("B", "PPSA2_00", PlatformCategory.PS5, play_duration=timedelta(hours=10)),
    ]
    games, _ = fetch_title_stats(FakeSource(stats), ["ps4", "ps5"], min_hours=1.0)
    trophies = {"CUSA1_00": FakeTrophy("CUSA1_00", 82), "PPSA2_00": FakeTrophy("PPSA2_00", 15)}
    source = FakeSource(stats, trophies)

    enriched = enrich_trophies(source, games, batch_size=5)
    assert enriched == 2
    by_id = {g.title_id: g for g in games}
    assert by_id["CUSA1_00"].completion_progress == 82.0
    assert by_id["PPSA2_00"].completion_progress == 15.0
