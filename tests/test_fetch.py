"""Tests for the psnawp layer, using stand-ins for TitleStats/TrophyTitle (no network)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest
from psnawp_api.models.title_stats import PlatformCategory

from psnstats.fetch import (
    WishlistUnavailableError,
    enrich_trophies,
    fetch_title_stats,
    fetch_wishlist,
    normalize_title_stat,
    normalize_wishlist_entry,
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


# --- wishlist (--wishlist) ---

# Shapes lifted from a real metGetStoreWishlist response.
PRODUCT_ENTRY = {
    "__typename": "Product",
    "id": "UP0006-PPSA08560_00-SPLITSTANDARDED0",
    "name": "Split Fiction",
    "platforms": ["PS5"],
    "storeDisplayClassification": "FULL_GAME",
    "localizedStoreDisplayClassification": "Full Game",
    "price": {
        "__typename": "SkuPrice",
        "basePrice": "$49.99",
        "discountedPrice": "$29.99",
        "discountText": "-40%",
        "isFree": False,
    },
    "boxArt": {"__typename": "Media", "url": "https://image.api.playstation.com/x.png"},
}
CONCEPT_ENTRY = {
    "__typename": "Concept",
    "id": "10000730",
    "name": "Grand Theft Auto VI",
    "platforms": [],
    "storeDisplayClassification": None,
    "localizedStoreDisplayClassification": None,
    "price": None,
    "boxArt": {"__typename": "Media", "url": "https://image.api.playstation.com/y.png"},
}


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class FakeAuthenticator:
    def __init__(self, payload=None, exc=None):
        self.payload = payload
        self.exc = exc
        self.calls = []

    def get(self, url, params=None, **kwargs):
        self.calls.append((url, params))
        if self.exc:
            raise self.exc
        return FakeResponse(self.payload)


class FakePsnawp:
    def __init__(self, payload=None, exc=None):
        self.authenticator = FakeAuthenticator(payload, exc)


def test_normalize_wishlist_product():
    item = normalize_wishlist_entry(PRODUCT_ENTRY)
    assert item.name == "Split Fiction"
    assert item.product_id == "UP0006-PPSA08560_00-SPLITSTANDARDED0"
    assert item.kind == "Product"
    assert item.platforms == ["PS5"]
    assert item.classification == "FULL_GAME"
    assert item.base_price == "$49.99"
    assert item.discounted_price == "$29.99"
    assert item.discount_text == "-40%"
    assert item.box_art_url.endswith("x.png")


def test_normalize_wishlist_concept_nulls():
    item = normalize_wishlist_entry(CONCEPT_ENTRY)
    assert item.kind == "Concept"
    assert item.platforms == []
    assert item.classification == ""
    assert item.base_price == ""
    assert item.discounted_price == ""
    assert item.product_id == "10000730"


def test_fetch_wishlist_happy_path():
    psnawp = FakePsnawp({"data": {"storeWishlist": [PRODUCT_ENTRY, CONCEPT_ENTRY]}})
    items = fetch_wishlist(psnawp)
    assert [i.name for i in items] == ["Split Fiction", "Grand Theft Auto VI"]
    url, params = psnawp.authenticator.calls[0]
    assert params["operationName"] == "metGetStoreWishlist"
    assert "sha256Hash" in params["extensions"]


def test_fetch_wishlist_empty_is_ok():
    psnawp = FakePsnawp({"data": {"storeWishlist": []}})
    assert fetch_wishlist(psnawp) == []


def test_fetch_wishlist_rotated_hash_raises():
    # PersistedQueryNotFound is what a rotated hash actually returns.
    psnawp = FakePsnawp({"errors": [{"message": "PersistedQueryNotFound"}], "data": None})
    with pytest.raises(WishlistUnavailableError, match="PersistedQueryNotFound"):
        fetch_wishlist(psnawp)


def test_fetch_wishlist_network_error_raises():
    psnawp = FakePsnawp(exc=RuntimeError("connection reset"))
    with pytest.raises(WishlistUnavailableError, match="connection reset"):
        fetch_wishlist(psnawp)


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
