"""Output writers: base library CSV/JSON and the analysis CSV.

Rendering (rounding playtime, formatting timestamps to a date) happens here, not
in the model, so the internal values stay full-precision.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .analysis import Game
from .fetch import WishlistItem

# Leading characters that a spreadsheet (Excel/Sheets) treats as a formula.
# Game titles and wishlist names are effectively free text, so neutralize any
# cell that starts with one to prevent CSV formula injection.
_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")


def _safe_cell(value):
    """Prefix a leading-formula string cell with ``'`` so it stays inert text."""
    if isinstance(value, str) and value and value[0] in _FORMULA_TRIGGERS:
        return "'" + value
    return value


# Base exporter columns (no --analyze needed).
LIBRARY_COLUMNS = [
    "title",
    "title_id",
    "system",
    "playtime_hours",
    "play_count",
    "last_played",
    "completion_progress",
]

# Wishlist export columns (--wishlist). Prices are Sony's localized display
# strings (e.g. "$19.99"); empty for Concepts (unreleased, no SKU).
WISHLIST_COLUMNS = [
    "name",
    "product_id",
    "kind",
    "platforms",
    "classification",
    "base_price",
    "discounted_price",
    "discount_text",
    "box_art_url",
]

# Enriched columns emitted with --analyze (documented in the README).
ANALYSIS_COLUMNS = [
    "title",
    "system",
    "playtime_hours",
    "play_count",
    "last_played",
    "enjoyment_score",
    "completion_ratio",
    "recency_days",
    "hours_per_session",
    "sessions_per_hour",
    "early_abandon",
    "late_abandon",
]


def _fmt_date(dt) -> str:
    """Render a datetime as a plain YYYY-MM-DD date (empty string if missing)."""
    return dt.strftime("%Y-%m-%d") if dt else ""


def game_to_dict(game: Game) -> dict:
    """Serialize a :class:`Game` for the base JSON export."""
    row = {
        "title": game.title,
        "title_id": game.title_id,
        "system": game.system,
        "playtime_hours": round(float(game.playtime_hours), 2),
        "play_count": int(game.play_count),
        "last_played": _fmt_date(game.last_played),
    }
    if game.completion_progress is not None:
        row["completion_progress"] = round(float(game.completion_progress), 1)
    return row


def write_json(games: list[Game], path: Path) -> int:
    """Write the base ``{"games": [...]}`` export. Returns row count."""
    payload = {"games": [game_to_dict(g) for g in games]}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return len(games)


def write_library_csv(games: list[Game], path: Path) -> int:
    """Write the base per-game CSV (exporter mode). Returns row count."""
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LIBRARY_COLUMNS)
        writer.writeheader()
        for g in games:
            row = game_to_dict(g)
            writer.writerow({col: _safe_cell(row.get(col, "")) for col in LIBRARY_COLUMNS})
    return len(games)


def write_analysis_csv(features: list[dict], path: Path) -> int:
    """Write the enriched 12-column CSV directly from feature rows.

    Rows come straight off the (already unique) per-game feature list, so titles
    that appear on both PS4 and PS5 never collide (the original title-keyed join
    silently dropped one of them).
    """
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=ANALYSIS_COLUMNS)
        writer.writeheader()
        for feat in features:
            flags = feat.get("abandonment_flags", {})
            last = feat.get("last_played") or ""
            writer.writerow(
                {
                    "title": _safe_cell(feat["title"]),
                    "system": feat["system"],
                    "playtime_hours": round(feat["playtime_hours"], 2),
                    "play_count": feat["play_count"],
                    "last_played": last[:10],
                    "enjoyment_score": feat["enjoyment_score"],
                    "completion_ratio": feat["completion_ratio"]
                    if feat["completion_ratio"] is not None
                    else "",
                    "recency_days": feat["recency_days"],
                    "hours_per_session": feat["hours_per_session"],
                    "sessions_per_hour": feat["sessions_per_hour"],
                    "early_abandon": flags.get("early_abandon", ""),
                    "late_abandon": flags.get("late_abandon", ""),
                }
            )
    return len(features)


def wishlist_item_to_dict(item: WishlistItem) -> dict:
    """Serialize a :class:`WishlistItem` for the wishlist JSON export."""
    return {
        "name": item.name,
        "product_id": item.product_id,
        "kind": item.kind,
        "platforms": item.platforms,
        "classification": item.classification,
        "base_price": item.base_price,
        "discounted_price": item.discounted_price,
        "discount_text": item.discount_text,
        "box_art_url": item.box_art_url,
    }


def write_wishlist_json(items: list[WishlistItem], path: Path) -> int:
    """Write ``{"wishlist": [...]}``. Returns row count."""
    payload = {"wishlist": [wishlist_item_to_dict(i) for i in items]}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return len(items)


def write_wishlist_csv(items: list[WishlistItem], path: Path) -> int:
    """Write the wishlist CSV (platforms joined with ``|``). Returns row count."""
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=WISHLIST_COLUMNS)
        writer.writeheader()
        for item in items:
            row = wishlist_item_to_dict(item)
            row["platforms"] = "|".join(item.platforms)
            writer.writerow({k: _safe_cell(v) for k, v in row.items()})
    return len(items)


def write_preferences(package: dict, path: Path) -> None:
    """Write the stable, un-dated ``preferences.json`` an agent can point at."""
    path.write_text(
        json.dumps(package, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8"
    )
