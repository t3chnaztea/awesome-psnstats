"""Human-facing renderers: the ASCII terminal report and a markdown variant.

Both are pure string builders (no printing, no color) so they are golden-file
testable and safe to embed in docs. Color, if any, is applied by the CLI.
"""

from __future__ import annotations

DIV_WIDTH = 70

TRAIT_LABELS = {
    "snackable_bias": "Snackable",
    "marathon_bias": "Marathon",
    "completionist_bias": "Completionist",
    "friction_tolerance": "Friction Tol",
    "variety_bias": "Variety",
}

_SORT_KEYS = {
    "enjoyment": (lambda g: g["enjoyment_score"], True),
    "hours": (lambda g: g["playtime_hours"], True),
    "recent": (lambda g: g["recency_score"], True),
    "title": (lambda g: g["title"].lower(), False),
}


def _sorted_games(per_game: list[dict], sort: str) -> list[dict]:
    key, reverse = _SORT_KEYS.get(sort, _SORT_KEYS["enjoyment"])
    return sorted(per_game, key=key, reverse=reverse)


def render_ascii_bar(value: float, width: int = 20) -> str:
    filled = int((value / 100) * width)
    filled = max(0, min(width, filled))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def _fmt_last(last_played) -> str:
    if not last_played:
        return "-"
    return str(last_played)[:7]


def render_ascii_report(
    package: dict, fetch_stats: dict, top: int = 10, sort: str = "enjoyment"
) -> str:
    """Build the terminal analysis report as a single string."""
    prefs = package["preferences"]
    summary = prefs["summary"]
    traits = prefs["traits"]
    agent = prefs["agent_features"]
    per_game = package["per_game_features"]

    lines: list[str] = []
    div = "=" * DIV_WIDTH
    rule = "-" * DIV_WIDTH

    lines.append(div)
    lines.append("ANALYSIS REPORT")
    lines.append(div)
    lines.append("")
    lines.append(f"fetch ok   : {fetch_stats.get('total_fetched', summary['game_count'])} games from API")
    lines.append(f"export ok  : {fetch_stats.get('included', summary['game_count'])} games kept")
    skipped_platform = fetch_stats.get("skipped_platform", 0)
    skipped_playtime = fetch_stats.get("skipped_playtime", 0)
    lines.append(f"             (skipped {skipped_platform} off-platform, {skipped_playtime} under threshold)")
    lines.append(f"analyze ok : {summary['game_count']} games")

    lines.append("")
    lines.append(rule)
    lines.append(f"TOP {top} GAMES (by {sort})")
    lines.append(rule)
    header = f"{'#':<3} {'Title':<30} {'Sys':<4} {'Score':<6} {'Hrs':<5} {'Plays':<6} {'Last':<8}"
    lines.append(header)
    lines.append(rule)
    for i, g in enumerate(_sorted_games(per_game, sort)[:top], 1):
        title = g["title"][:28] + ".." if len(g["title"]) > 30 else g["title"]
        last = _fmt_last(g.get("last_played"))
        lines.append(
            f"{i:<3} {title:<30} {g['system']:<4} {g['enjoyment_score']:<6.1f} "
            f"{g['playtime_hours']:<5.0f} {g['play_count']:<6} {last:<8}"
        )

    lines.append("")
    lines.append(rule)
    lines.append("PLAYER TRAITS")
    lines.append(rule)
    for trait_key, label in TRAIT_LABELS.items():
        trait = traits[trait_key]
        bar = render_ascii_bar(trait["value"])
        raw = trait.get("raw_metric", "")
        lines.append(f"{label:<14} {bar} {trait['value']:>5.1f}  ({raw})")

    lines.append("")
    lines.append(rule)
    lines.append("PLAY STYLE")
    lines.append(rule)
    lines.append(f"Session style      : {agent['preferred_session_style']}")
    lines.append(f"Commitment style   : {agent['preferred_commitment_style']}")
    pr = agent["platform_recency"]
    lines.append(f"Platform recency   : PS5 {pr['PS5']:.0f}% / PS4 {pr['PS4']:.0f}%")

    lines.append("")
    lines.append(rule)
    lines.append("SIGNALS")
    lines.append(rule)
    lines.append("")
    lines.append("Positive:")
    if agent["positive_signals"]:
        lines.extend(f"  + {sig}" for sig in agent["positive_signals"])
    else:
        lines.append("  (none detected)")
    lines.append("")
    lines.append("Avoid:")
    if agent["avoid_signals"]:
        lines.extend(f"  - {sig}" for sig in agent["avoid_signals"])
    else:
        lines.append("  (none detected)")
    lines.append("")
    lines.append(div)
    return "\n".join(lines)


def render_markdown_report(package: dict, top: int = 10, sort: str = "enjoyment") -> str:
    """Build a markdown analysis report (``--format md``)."""
    prefs = package["preferences"]
    summary = prefs["summary"]
    traits = prefs["traits"]
    agent = prefs["agent_features"]
    per_game = package["per_game_features"]

    lines: list[str] = []
    lines.append("# PlayStation Taste Profile")
    lines.append("")
    lines.append(
        f"**{summary['game_count']} games** analyzed, "
        f"**{summary['total_playtime_hours']:.0f} hours** total playtime."
    )
    lines.append("")
    lines.append(f"## Top {top} games (by {sort})")
    lines.append("")
    for i, g in enumerate(_sorted_games(per_game, sort)[:top], 1):
        lines.append(
            f"{i}. **{g['title']}** ({g['system']}) — score {g['enjoyment_score']:.1f}, "
            f"{g['playtime_hours']:.0f}h, {g['play_count']} plays"
        )
    lines.append("")
    lines.append("## Player traits")
    lines.append("")
    for trait_key, label in TRAIT_LABELS.items():
        trait = traits[trait_key]
        lines.append(f"- **{label}**: {trait['value']:.1f} ({trait.get('raw_metric', '')})")
    lines.append("")
    lines.append("## Play style")
    lines.append("")
    lines.append(f"- Session style: {agent['preferred_session_style']}")
    lines.append(f"- Commitment style: {agent['preferred_commitment_style']}")
    pr = agent["platform_recency"]
    lines.append(f"- Platform recency: PS5 {pr['PS5']:.0f}% / PS4 {pr['PS4']:.0f}%")
    lines.append("")
    if agent["positive_signals"]:
        lines.append("## What to recommend")
        lines.append("")
        lines.extend(f"- {sig}" for sig in agent["positive_signals"])
        lines.append("")
    if agent["avoid_signals"]:
        lines.append("## What to avoid")
        lines.append("")
        lines.extend(f"- {sig}" for sig in agent["avoid_signals"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
