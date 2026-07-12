#!/usr/bin/env python3
"""Regenerate the example artifacts from a SYNTHETIC library.

The data here is fabricated (real game titles, invented playtimes/dates/counts):
no real account, no real play history. Run from anywhere:

    python examples/generate.py

It writes library.csv, preferences.json, and report.md next to this file.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from psnstats.analysis import Game, analyze_preferences
from psnstats.report import render_markdown_report
from psnstats.writers import write_analysis_csv, write_preferences

# Fixed clock so the committed examples are byte-stable across regenerations.
NOW = datetime(2026, 7, 12, 12, 0, 0)


def _ago(days: int) -> datetime:
    return NOW - timedelta(days=days)


# (title, title_id, system, hours, plays, days_since_played, completion%)
FIXTURES = [
    ("Elden Ring", "PPSA01234_00", "PS5", 120.0, 340, 4, 78),
    ("Bloodborne", "CUSA00900_00", "PS4", 62.0, 90, 60, 95),
    ("God of War Ragnarok", "PPSA01512_00", "PS5", 45.0, 60, 20, 88),
    ("Hades", "PPSA02020_00", "PS5", 38.0, 210, 9, 62),
    ("Stardew Valley", "CUSA05563_00", "PS4", 90.0, 180, 15, 40),
    ("Returnal", "PPSA01337_00", "PS5", 30.0, 75, 33, 55),
    ("Disco Elysium - The Final Cut", "PPSA02719_00", "PS5", 24.0, 20, 40, 100),
    ("Minecraft", "CUSA00744_00", "PS4", 55.0, 300, 120, 20),
    ("Minecraft", "PPSA04593_00", "PS5", 18.0, 60, 6, 15),
    ("Sekiro: Shadows Die Twice", "CUSA09564_00", "PS4", 40.0, 88, 200, 30),
    ("Untitled Goose Game", "CUSA14930_00", "PS4", 6.0, 12, 45, 100),
    ("Cyberpunk 2077", "PPSA01522_00", "PS5", 80.0, 110, 70, 70),
    ("Death Stranding", "CUSA13780_00", "PS4", 15.0, 20, 300, 12),
    ("Tetris Effect", "CUSA11704_00", "PS4", 12.0, 140, 2, 45),
]


def build_library() -> list[Game]:
    return [
        Game(
            title=title,
            title_id=title_id,
            system=system,
            playtime_hours=hours,
            play_count=plays,
            last_played=_ago(days),
            completion_progress=completion,
        )
        for (title, title_id, system, hours, plays, days, completion) in FIXTURES
    ]


def main() -> None:
    here = Path(__file__).resolve().parent
    games = build_library()
    package = analyze_preferences(games, source_file="psn_export_example.json", now=NOW)

    write_analysis_csv(package["per_game_features"], here / "library.csv")
    write_preferences(package, here / "preferences.json")
    (here / "report.md").write_text(render_markdown_report(package), encoding="utf-8")
    print(f"wrote example artifacts to {here}/")


if __name__ == "__main__":
    main()
