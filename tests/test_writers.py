"""Golden round-trip tests for the CSV/JSON writers."""

from __future__ import annotations

import csv
import json

from conftest import make_game
from psnstats.analysis import analyze_preferences
from psnstats.fetch import WishlistItem
from psnstats.writers import (
    ANALYSIS_COLUMNS,
    LIBRARY_COLUMNS,
    WISHLIST_COLUMNS,
    write_analysis_csv,
    write_json,
    write_library_csv,
    write_preferences,
    write_wishlist_csv,
    write_wishlist_json,
)


def _library():
    return [
        make_game(title="Bloodborne", title_id="CUSA00900_00", system="PS4",
                  playtime_hours=42.6, play_count=7),
        make_game(title="Returnal", title_id="PPSA01512_00", system="PS5",
                  playtime_hours=30.2, play_count=12),
    ]


def test_library_csv_round_trip(tmp_path):
    path = tmp_path / "lib.csv"
    rows = write_library_csv(_library(), path)
    assert rows == 2
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == LIBRARY_COLUMNS
        data = list(reader)
    assert data[0]["title"] == "Bloodborne"
    assert data[0]["title_id"] == "CUSA00900_00"
    assert data[0]["playtime_hours"] == "42.6"
    assert data[0]["last_played"] == "2026-07-12"


def test_json_round_trip(tmp_path):
    path = tmp_path / "export.json"
    write_json(_library(), path)
    payload = json.loads(path.read_text())
    assert len(payload["games"]) == 2
    assert payload["games"][0]["title"] == "Bloodborne"
    assert payload["games"][0]["playtime_hours"] == 42.6


def test_duplicate_title_across_platforms_does_not_collide(tmp_path, now):
    """Port fix 1: a title on both PS4 and PS5 must produce two CSV rows."""
    games = [
        make_game(title="Minecraft", title_id="CUSA00744_00", system="PS4", playtime_hours=100.0),
        make_game(title="Minecraft", title_id="PPSA04593_00", system="PS5", playtime_hours=50.0),
    ]
    pkg = analyze_preferences(games, now=now)
    path = tmp_path / "analysis.csv"
    rows = write_analysis_csv(pkg["per_game_features"], path)
    assert rows == 2
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == ANALYSIS_COLUMNS
        data = list(reader)
    systems = sorted(r["system"] for r in data)
    assert systems == ["PS4", "PS5"]  # both survived, no title-keyed collision


def test_analysis_csv_has_enrichment_columns(tmp_path, now):
    games = [make_game(title="A", title_id="CUSA1_00", playtime_hours=10.0, completion_progress=80)]
    pkg = analyze_preferences(games, now=now)
    path = tmp_path / "analysis.csv"
    write_analysis_csv(pkg["per_game_features"], path)
    with path.open(newline="") as f:
        row = next(csv.DictReader(f))
    assert row["completion_ratio"] == "0.8"
    assert row["enjoyment_score"] != ""


def test_preferences_json_is_stable_sorted(tmp_path, now):
    pkg = analyze_preferences(_library(), now=now)
    path = tmp_path / "preferences.json"
    write_preferences(pkg, path)
    reloaded = json.loads(path.read_text())
    assert reloaded["schema_version"] == "1.0"
    assert "traits" in reloaded["preferences"]
    # sort_keys makes the serialization deterministic across runs.
    assert path.read_text() == json.dumps(pkg, indent=2, sort_keys=True, ensure_ascii=False)


def _wishlist():
    return [
        WishlistItem(name="Split Fiction", product_id="UP0006-PPSA08560_00-SPLITSTANDARDED0",
                     kind="Product", platforms=["PS4", "PS5"],
                     classification="FULL_GAME", box_art_url="https://img/x.png"),
        WishlistItem(name="Grand Theft Auto VI", product_id="10000730", kind="Concept"),
    ]


def test_wishlist_csv_round_trip(tmp_path):
    path = tmp_path / "wishlist.csv"
    rows = write_wishlist_csv(_wishlist(), path)
    assert rows == 2
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == WISHLIST_COLUMNS
        data = list(reader)
    assert data[0]["name"] == "Split Fiction"
    assert data[0]["platforms"] == "PS4|PS5"
    assert data[1]["kind"] == "Concept"
    assert data[1]["classification"] == ""


def test_wishlist_json_round_trip(tmp_path):
    path = tmp_path / "wishlist.json"
    rows = write_wishlist_json(_wishlist(), path)
    assert rows == 2
    payload = json.loads(path.read_text())
    assert [i["name"] for i in payload["wishlist"]] == ["Split Fiction", "Grand Theft Auto VI"]
    assert payload["wishlist"][0]["platforms"] == ["PS4", "PS5"]


def test_library_csv_neutralizes_formula_injection(tmp_path):
    """A title starting with a formula trigger is written as inert text."""
    games = [
        make_game(title="=HYPERLINK(\"http://evil\")", title_id="X1", system="PS5",
                  playtime_hours=3.0, play_count=1),
        make_game(title="The Last of Us", title_id="X2", system="PS4",
                  playtime_hours=5.0, play_count=2),
    ]
    path = tmp_path / "lib.csv"
    write_library_csv(games, path)
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["title"] == "'=HYPERLINK(\"http://evil\")"  # prefixed, inert
    assert rows[1]["title"] == "The Last of Us"  # normal title untouched


def test_wishlist_csv_neutralizes_formula_injection(tmp_path):
    item = WishlistItem(name="@SUM(1+1)", product_id="P1", kind="Product",
                        platforms=["PS5"], base_price="$19.99")
    path = tmp_path / "wishlist.csv"
    write_wishlist_csv([item], path)
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["name"] == "'@SUM(1+1)"
