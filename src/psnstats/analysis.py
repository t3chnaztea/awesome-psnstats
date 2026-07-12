"""Pure taste-analysis engine.

No psnawp import lives here: everything operates on the normalized :class:`Game`
model and plain values, so it is fully unit-testable with zero network and could
be reused for a Steam adapter later. Internally playtime stays a float and
``last_played`` stays a full timestamp; rounding/formatting happens at render time
(see :mod:`psnstats.report` and :mod:`psnstats.writers`).
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone

# Division-by-zero guard.
EPS = 1e-6
# Recency decay: a game last played this many days ago scores ~0.37.
HALF_LIFE_DAYS = 90
# Enjoyment score weights (must sum to 1.0).
ENJOYMENT_WEIGHTS = {
    "playtime_log": 0.35,
    "recency": 0.25,
    "completion": 0.20,
    "replay": 0.20,
}
# Points subtracted from enjoyment when an abandonment flag fires.
ABANDONMENT_PENALTY = {
    "early": 15,
    "late": 10,
}
# Fallback recency when a game has never reported a last-played date.
NO_PLAY_RECENCY_DAYS = 365 * 2


@dataclass
class Game:
    """A single title, normalized out of the PSN API surface.

    ``completion_progress`` is a 0-100 trophy-completion percentage and is only
    populated when the caller opted into trophy enrichment (``--trophies``);
    otherwise it stays ``None`` and completion-dependent signals go neutral.
    """

    title: str
    title_id: str
    system: str
    playtime_hours: float
    play_count: int
    last_played: datetime | None = None
    completion_progress: float | None = None

    @property
    def key(self) -> str:
        """Stable per-row identity that never collides across platforms."""
        return self.title_id or f"{self.title}::{self.system}"


def safe_float(val, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def percentile_scale(
    values: list[float], value: float, floor: float = 5, ceiling: float = 95
) -> float:
    """Scale ``value`` to 0-100 by its percentile rank in ``values``."""
    if not values or len(values) < 2:
        return 50.0

    n = len(values)
    below = sum(1 for v in values if v < value)
    equal = sum(1 for v in values if v == value)
    percentile = ((below + 0.5 * equal) / n) * 100
    return max(floor, min(ceiling, percentile))


def compute_entropy(counts: list[int]) -> float:
    """Normalized Shannon entropy (0-1) over a list of counts."""
    total = sum(counts)
    if total == 0 or len(counts) <= 1:
        return 0.0

    probs = [c / total for c in counts if c > 0]
    entropy = -sum(p * math.log(p) for p in probs)
    max_entropy = math.log(len(probs))
    if max_entropy == 0:
        return 0.0
    return entropy / max_entropy


def compute_per_game_features(game: Game, now: datetime) -> dict:
    """Derive the per-game feature row used by scoring, traits, and the CSV."""
    playtime_hours = float(game.playtime_hours)
    play_count = int(game.play_count)

    completion_ratio = None
    if game.completion_progress is not None:
        completion_ratio = safe_float(game.completion_progress) / 100.0

    sessions_per_hour = play_count / max(playtime_hours, EPS)
    hours_per_session = playtime_hours / max(play_count, 1)

    progress_velocity = None
    if game.completion_progress is not None:
        progress_velocity = safe_float(game.completion_progress) / max(playtime_hours, EPS)

    last_played = game.last_played
    if last_played is not None:
        # Guard against a naive/aware mismatch between the stored timestamp and
        # the analysis clock; compare both as naive.
        if (last_played.tzinfo is None) != (now.tzinfo is None):
            last_played = last_played.replace(tzinfo=None)
            now = now.replace(tzinfo=None)
        recency_days = max(0, (now - last_played).days)
    else:
        recency_days = NO_PLAY_RECENCY_DAYS
    recency_score = math.exp(-recency_days / HALF_LIFE_DAYS)

    early_abandon = False
    late_abandon = False
    if game.completion_progress is not None:
        progress = safe_float(game.completion_progress)
        if progress < 20 and play_count >= 3:
            early_abandon = True
        if playtime_hours >= 10 and progress < 40:
            late_abandon = True

    playtime_log_score = min(math.log(max(playtime_hours, 1) + 1) / math.log(200), 1.0) * 100
    recency_component = recency_score * 100
    completion_component = completion_ratio * 100 if completion_ratio is not None else 50

    replay_component = 0
    if play_count > 1:
        replay_component = min((play_count - 1) * 10, 50)
    if playtime_hours > 20:
        replay_component += 20
    if playtime_hours > 50:
        replay_component += 30
    replay_component = min(replay_component, 100)

    enjoyment_score = (
        ENJOYMENT_WEIGHTS["playtime_log"] * playtime_log_score
        + ENJOYMENT_WEIGHTS["recency"] * recency_component
        + ENJOYMENT_WEIGHTS["completion"] * completion_component
        + ENJOYMENT_WEIGHTS["replay"] * replay_component
    )
    if early_abandon:
        enjoyment_score -= ABANDONMENT_PENALTY["early"]
    if late_abandon:
        enjoyment_score -= ABANDONMENT_PENALTY["late"]
    enjoyment_score = max(0, min(100, enjoyment_score))

    return {
        "title": game.title,
        "title_id": game.title_id,
        "system": game.system,
        "playtime_hours": playtime_hours,
        "play_count": play_count,
        "hours_per_session": round(hours_per_session, 2),
        "sessions_per_hour": round(sessions_per_hour, 3),
        "completion_ratio": round(completion_ratio, 3) if completion_ratio is not None else None,
        "progress_velocity": round(progress_velocity, 3) if progress_velocity is not None else None,
        "recency_days": recency_days,
        "recency_score": round(recency_score, 3),
        "last_played": game.last_played.isoformat() if game.last_played else None,
        "abandonment_flags": {"early_abandon": early_abandon, "late_abandon": late_abandon},
        "enjoyment_score": round(enjoyment_score, 1),
    }


@dataclass
class Preferences:
    """Result of :func:`analyze_preferences` (also the preferences.json shape)."""

    package: dict = field(default_factory=dict)


def analyze_preferences(
    games: list[Game], source_file: str = "", now: datetime | None = None
) -> dict:
    """Build the full preferences package: summary, five traits, agent features.

    ``now`` is injectable so tests are deterministic. Raises ``ValueError`` if
    there is nothing to analyze.
    """
    if now is None:
        # Naive UTC to match the normalized (naive-UTC) last_played timestamps.
        now = datetime.now(timezone.utc).replace(tzinfo=None)

    notes: list[str] = []
    per_game_features: list[dict] = []
    for game in games:
        try:
            per_game_features.append(compute_per_game_features(game, now))
        except Exception as exc:  # noqa: BLE001 - one bad row shouldn't kill the run
            notes.append(f"Skipped game '{game.title}': {exc}")

    if not per_game_features:
        raise ValueError("No games to analyze")

    notes.append(f"EPS={EPS} used to avoid division by zero")
    notes.append(f"HALF_LIFE_DAYS={HALF_LIFE_DAYS} for recency decay")
    notes.append("Traits scaled using percentile distribution (floor=5, ceiling=95)")

    game_count = len(per_game_features)
    total_playtime = sum(g["playtime_hours"] for g in per_game_features)

    systems: dict[str, dict] = {}
    for g in per_game_features:
        sys_name = g["system"]
        bucket = systems.setdefault(sys_name, {"count": 0, "playtime_hours": 0.0})
        bucket["count"] += 1
        bucket["playtime_hours"] += g["playtime_hours"]

    sorted_by_enjoyment = sorted(per_game_features, key=lambda x: x["enjoyment_score"], reverse=True)
    top_games = [
        {"title": g["title"], "system": g["system"], "enjoyment_score": g["enjoyment_score"]}
        for g in sorted_by_enjoyment[:10]
    ]
    sorted_by_recency = sorted(per_game_features, key=lambda x: x["recency_score"], reverse=True)
    recent_games = [
        {"title": g["title"], "system": g["system"], "recency_score": g["recency_score"]}
        for g in sorted_by_recency[:10]
    ]

    sph_values = [g["sessions_per_hour"] for g in per_game_features]
    hps_values = [g["hours_per_session"] for g in per_game_features]

    avg_sph = statistics.mean(sph_values)
    median_sph = statistics.median(sph_values)
    snackable_bias = percentile_scale(sph_values, avg_sph)
    snackable_contributors = [
        g["title"]
        for g in sorted(per_game_features, key=lambda x: x["sessions_per_hour"], reverse=True)[:3]
    ]

    avg_hps = statistics.mean(hps_values)
    median_hps = statistics.median(hps_values)
    marathon_bias = percentile_scale(hps_values, avg_hps)
    marathon_contributors = [
        g["title"]
        for g in sorted(per_game_features, key=lambda x: x["hours_per_session"], reverse=True)[:3]
    ]

    completion_values = [
        g["completion_ratio"] for g in per_game_features if g["completion_ratio"] is not None
    ]
    if completion_values:
        avg_completion = statistics.mean(completion_values)
        completionist_bias = percentile_scale(completion_values, avg_completion)
        completionist_contributors = [
            g["title"]
            for g in sorted(
                (x for x in per_game_features if x["completion_ratio"] is not None),
                key=lambda x: x["completion_ratio"],
                reverse=True,
            )[:3]
        ]
    else:
        completionist_bias = 50
        avg_completion = None
        completionist_contributors = []
        notes.append(
            "No completion data available (run with --trophies); "
            "completionist_bias set to neutral 50"
        )

    early_abandon_count = sum(
        1 for g in per_game_features if g["abandonment_flags"]["early_abandon"]
    )
    late_abandon_count = sum(1 for g in per_game_features if g["abandonment_flags"]["late_abandon"])
    early_abandon_rate = early_abandon_count / max(game_count, 1)
    late_abandon_rate = late_abandon_count / max(game_count, 1)
    total_abandon_rate = (early_abandon_count + late_abandon_count) / max(game_count, 1)
    friction_tolerance = max(5, min(95, 95 - (total_abandon_rate * 180)))
    friction_contributors = [
        g["title"]
        for g in per_game_features
        if not g["abandonment_flags"]["early_abandon"] and not g["abandonment_flags"]["late_abandon"]
    ][:3]

    system_counts = [v["count"] for v in systems.values()]
    variety_entropy = compute_entropy(system_counts)
    variety_bias = variety_entropy * 90 + 5
    variety_contributors = list(systems.keys())

    ps5_recency_playtime = sum(
        g["playtime_hours"] * g["recency_score"]
        for g in per_game_features
        if g["system"] == "PS5"
    )
    ps4_recency_playtime = sum(
        g["playtime_hours"] * g["recency_score"]
        for g in per_game_features
        if g["system"] == "PS4"
    )
    total_recency_playtime = ps5_recency_playtime + ps4_recency_playtime
    ps5_recency_pct = (ps5_recency_playtime / max(total_recency_playtime, EPS)) * 100
    ps4_recency_pct = (ps4_recency_playtime / max(total_recency_playtime, EPS)) * 100

    traits = {
        "snackable_bias": {
            "value": round(snackable_bias, 1),
            "raw_metric": f"sessions/hr: {median_sph:.2f} median",
            "explanation": f"Based on median {median_sph:.2f} sessions/hour",
            "contributors": snackable_contributors,
        },
        "marathon_bias": {
            "value": round(marathon_bias, 1),
            "raw_metric": f"hrs/session: {median_hps:.1f} median",
            "explanation": f"Based on median {median_hps:.1f} hours/session",
            "contributors": marathon_contributors,
        },
        "completionist_bias": {
            "value": round(completionist_bias, 1),
            "raw_metric": f"completion: {avg_completion * 100:.0f}% avg"
            if avg_completion is not None
            else "no data",
            "explanation": "Based on avg completion ratio"
            if completion_values
            else "No completion data (run with --trophies)",
            "contributors": completionist_contributors,
        },
        "friction_tolerance": {
            "value": round(friction_tolerance, 1),
            "raw_metric": f"early: {early_abandon_rate * 100:.0f}%, late: {late_abandon_rate * 100:.0f}%",
            "explanation": f"{early_abandon_count} early + {late_abandon_count} late abandons / {game_count} games",
            "contributors": friction_contributors,
        },
        "variety_bias": {
            "value": round(variety_bias, 1),
            "raw_metric": f"entropy: {variety_entropy:.2f}",
            "explanation": f"Entropy across {len(systems)} systems",
            "contributors": variety_contributors,
        },
    }

    if snackable_bias > marathon_bias + 15:
        preferred_session_style = "snackable"
    elif marathon_bias > snackable_bias + 15:
        preferred_session_style = "marathon"
    else:
        preferred_session_style = "mixed"

    if completionist_bias > 65:
        preferred_commitment_style = "finisher"
    elif completionist_bias < 35:
        preferred_commitment_style = "tourist"
    else:
        preferred_commitment_style = "mixed"

    positive_signals: list[str] = []
    avoid_signals: list[str] = []

    if median_hps > 2.0:
        positive_signals.append(f"long-session games: median session {median_hps:.1f}h")
    elif median_hps < 1.0:
        positive_signals.append(f"short-session loops: median session {median_hps:.1f}h")
    if completionist_bias > 60 and completion_values:
        positive_signals.append(f"completable games: avg completion {avg_completion * 100:.0f}%")
    if ps5_recency_pct > 65:
        positive_signals.append(
            f"favors PS5 lately: {ps5_recency_pct:.0f}% recency-weighted playtime"
        )
    elif ps4_recency_pct > 65:
        positive_signals.append(
            f"favors PS4 lately: {ps4_recency_pct:.0f}% recency-weighted playtime"
        )
    if friction_tolerance > 70:
        positive_signals.append(
            f"handles difficult progression: {total_abandon_rate * 100:.0f}% abandon rate"
        )

    if early_abandon_rate > 0.15:
        avoid_signals.append(f"slow early game: {early_abandon_rate * 100:.0f}% early abandon rate")
    if late_abandon_rate > 0.10:
        avoid_signals.append(f"drawn-out mid-game: {late_abandon_rate * 100:.0f}% late abandon rate")
    if median_hps > 2.5 and marathon_bias < 40:
        avoid_signals.append("long-session requirement: drops off when session > 2.5h")
    if median_sph > 1.5 and snackable_bias < 40:
        avoid_signals.append(f"too-fragmented sessions: median {median_sph:.1f} sessions/hr")

    agent_features = {
        "preferred_session_style": preferred_session_style,
        "preferred_commitment_style": preferred_commitment_style,
        "platform_recency": {"PS5": round(ps5_recency_pct, 1), "PS4": round(ps4_recency_pct, 1)},
        "positive_signals": positive_signals,
        "avoid_signals": avoid_signals,
        "weights": {
            "enjoyment": ENJOYMENT_WEIGHTS,
            "abandonment_penalty": ABANDONMENT_PENALTY,
            "half_life_days": HALF_LIFE_DAYS,
            "thresholds": {
                "snackable_vs_marathon_delta": 15,
                "finisher_threshold": 65,
                "tourist_threshold": 35,
            },
        },
    }

    return {
        "schema_version": "1.0",
        "generated_at": now.isoformat(),
        "source": {"system": "playstation", "file": source_file},
        "preferences": {
            "summary": {
                "game_count": game_count,
                "total_playtime_hours": round(total_playtime, 1),
                "systems": {
                    k: {"count": v["count"], "playtime_hours": round(v["playtime_hours"], 1)}
                    for k, v in systems.items()
                },
                "top_games": top_games,
                "recent_games": recent_games,
            },
            "traits": traits,
            "agent_features": agent_features,
        },
        "per_game_features": per_game_features,
        "notes": notes,
    }
