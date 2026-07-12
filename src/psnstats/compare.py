"""Delta between two preferences packages (the monthly-rerun feature).

Pure: takes two already-parsed ``preferences.json`` dicts and reports what
changed. Keyed on ``title_id`` when present, falling back to ``title::system``.
"""

from __future__ import annotations

from .report import TRAIT_LABELS

# How much a trait must move (0-100 scale) before we call it drift.
TRAIT_DRIFT_THRESHOLD = 3.0


def _feature_key(feat: dict) -> str:
    tid = feat.get("title_id")
    if tid:
        return tid
    return f"{feat.get('title')}::{feat.get('system')}"


def _index(package: dict) -> dict[str, dict]:
    return {_feature_key(f): f for f in package.get("per_game_features", [])}


def compare_packages(old: dict, new: dict) -> dict:
    """Compute the delta from ``old`` to ``new``.

    Returns new titles, per-title hours gained (only titles that moved), total
    hours gained, and trait drift for each of the five traits.
    """
    old_idx = _index(old)
    new_idx = _index(new)

    new_titles = [
        {"title": f["title"], "system": f["system"], "playtime_hours": f["playtime_hours"]}
        for key, f in new_idx.items()
        if key not in old_idx
    ]
    new_titles.sort(key=lambda x: x["playtime_hours"], reverse=True)

    hours_gained: list[dict] = []
    total_hours_gained = 0.0
    for key, nf in new_idx.items():
        old_hours = old_idx[key]["playtime_hours"] if key in old_idx else 0.0
        delta = round(nf["playtime_hours"] - old_hours, 2)
        if abs(delta) >= 0.01:
            total_hours_gained += delta
            hours_gained.append(
                {"title": nf["title"], "system": nf["system"], "hours_gained": delta}
            )
    hours_gained.sort(key=lambda x: x["hours_gained"], reverse=True)

    old_traits = old.get("preferences", {}).get("traits", {})
    new_traits = new.get("preferences", {}).get("traits", {})
    trait_drift: dict[str, dict] = {}
    for trait_key, label in TRAIT_LABELS.items():
        old_val = old_traits.get(trait_key, {}).get("value")
        new_val = new_traits.get(trait_key, {}).get("value")
        if old_val is None or new_val is None:
            continue
        delta = round(new_val - old_val, 1)
        trait_drift[trait_key] = {
            "label": label,
            "old": old_val,
            "new": new_val,
            "delta": delta,
            "moved": abs(delta) >= TRAIT_DRIFT_THRESHOLD,
        }

    return {
        "new_titles": new_titles,
        "removed_count": sum(1 for key in old_idx if key not in new_idx),
        "hours_gained": hours_gained,
        "total_hours_gained": round(total_hours_gained, 1),
        "trait_drift": trait_drift,
    }


def render_compare(delta: dict, top: int = 10) -> str:
    """Render a compare delta as a plain-text block."""
    lines: list[str] = []
    div = "=" * 70
    lines.append(div)
    lines.append("COMPARE (delta vs previous export)")
    lines.append(div)
    lines.append("")

    nt = delta["new_titles"]
    lines.append(f"New titles: {len(nt)}")
    for t in nt[:top]:
        lines.append(f"  + {t['title']} ({t['system']}) — {t['playtime_hours']:.0f}h")
    if delta["removed_count"]:
        lines.append(f"Titles no longer present: {delta['removed_count']}")
    lines.append("")

    lines.append(f"Total hours gained: {delta['total_hours_gained']:+.1f}")
    for h in delta["hours_gained"][:top]:
        lines.append(f"  {h['hours_gained']:+.1f}h  {h['title']} ({h['system']})")
    lines.append("")

    lines.append("Trait drift:")
    any_moved = False
    for info in delta["trait_drift"].values():
        marker = "*" if info["moved"] else " "
        if info["moved"]:
            any_moved = True
        lines.append(
            f" {marker} {info['label']:<14} {info['old']:>5.1f} -> {info['new']:>5.1f}  ({info['delta']:+.1f})"
        )
    if not any_moved:
        lines.append("  (no trait moved beyond threshold)")
    lines.append("")
    lines.append(div)
    return "\n".join(lines)
