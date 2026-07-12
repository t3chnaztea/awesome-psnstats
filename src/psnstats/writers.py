"""Output writers: base library CSV/JSON and the analysis CSV.

Rendering (rounding playtime, formatting timestamps to a date) happens here, not
in the model, so the internal values stay full-precision.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .analysis import Game

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
            writer.writerow({col: row.get(col, "") for col in LIBRARY_COLUMNS})
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
                    "title": feat["title"],
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


def write_preferences(package: dict, path: Path) -> None:
    """Write the stable, un-dated ``preferences.json`` an agent can point at."""
    path.write_text(
        json.dumps(package, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8"
    )
