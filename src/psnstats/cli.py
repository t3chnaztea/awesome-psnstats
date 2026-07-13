"""Command-line entry point: argument parsing, orchestration, exit codes.

Exit codes: 0 ok / 1 fatal / 2 auth / 3 nothing matched.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

from . import __version__
from .analysis import analyze_preferences
from .compare import compare_packages, render_compare
from .fetch import (
    AuthError,
    ForbiddenError,
    UserNotFoundError,
    WishlistUnavailableError,
    authenticate,
    enrich_trophies,
    fetch_title_stats,
    fetch_wishlist,
    resolve_source,
)
from .report import render_ascii_report, render_markdown_report
from .writers import (
    write_analysis_csv,
    write_json,
    write_library_csv,
    write_preferences,
    write_wishlist_csv,
    write_wishlist_json,
)

EXIT_OK = 0
EXIT_FATAL = 1
EXIT_AUTH = 2
EXIT_NOTHING = 3

DEFAULT_CONFIG_NPSSO = Path.home() / ".config" / "psnstats" / "npsso"
VALID_PLATFORMS = {"ps4", "ps5", "other"}
VALID_FORMATS = {"csv", "json", "md", "all"}

NPSSO_URL = "https://ca.account.sony.com/api/v1/ssocookie"


class Palette:
    """ANSI color, auto-disabled off a TTY, under NO_COLOR, or with --no-color."""

    def __init__(self, enabled: bool):
        self.enabled = enabled

    def _wrap(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else text

    def bold(self, t):
        return self._wrap("1", t)

    def dim(self, t):
        return self._wrap("2", t)

    def green(self, t):
        return self._wrap("32", t)

    def yellow(self, t):
        return self._wrap("33", t)

    def red(self, t):
        return self._wrap("31", t)

    def cyan(self, t):
        return self._wrap("36", t)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="psnstats",
        description="Export your PlayStation Network play history to CSV/JSON and "
        "optionally build an LLM-ready taste profile, entirely on your machine.",
        epilog=f"Get your NPSSO token: log in to PSN, then visit {NPSSO_URL}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    auth = p.add_argument_group("authentication (precedence: --npsso > --npsso-file > $PSN_NPSSO)")
    auth.add_argument(
        "--npsso",
        metavar="TOKEN",
        help="NPSSO token, passed inline (lands in shell history and `ps` output; "
        "prefer --npsso-file or $PSN_NPSSO)",
    )
    auth.add_argument(
        "--npsso-file",
        metavar="PATH",
        help=f"read NPSSO from a file (default probe: {DEFAULT_CONFIG_NPSSO}; chmod 600 it)",
    )

    scope = p.add_argument_group("scope")
    scope.add_argument(
        "--user",
        metavar="ONLINE_ID",
        help="export another account's public library instead of your own",
    )
    scope.add_argument(
        "--platforms",
        default="ps4,ps5",
        metavar="LIST",
        help="comma list of ps4,ps5,other (default: ps4,ps5). "
        "PS3/Vita playtime does not exist in Sony's API.",
    )
    scope.add_argument(
        "--min-hours",
        type=float,
        default=1.0,
        metavar="N",
        help="skip titles under N hours (default: 1; use 0 for a full dump)",
    )
    scope.add_argument(
        "--limit", type=int, metavar="N", help="stop after N kept titles (test/demo runs)"
    )
    scope.add_argument(
        "--wishlist",
        action="store_true",
        help="also export your store wishlist to wishlist.csv/wishlist.json "
        "(own account only; Sony exposes no public wishlist, so this cannot "
        "combine with --user)",
    )

    enrich = p.add_argument_group("enrichment")
    enrich.add_argument(
        "--trophies",
        action="store_true",
        help="fetch trophy completion (fills completion/abandonment; ~80 extra "
        "requests on a 400-game library)",
    )

    analysis = p.add_argument_group("analysis")
    analysis.add_argument(
        "--analyze",
        action="store_true",
        help="compute the taste profile: preferences.json, five traits, report (default: off)",
    )
    analysis.add_argument(
        "--compare",
        metavar="PATH",
        help="diff this run against a previous preferences.json (implies --analyze)",
    )

    output = p.add_argument_group("output")
    output.add_argument(
        "--output", default="./psn-export", metavar="DIR", help="output directory (default: ./psn-export)"
    )
    output.add_argument(
        "--format",
        default="csv,json",
        metavar="LIST",
        help="comma list of csv,json,md,all (default: csv,json). "
        "md is the analysis report and implies --analyze; "
        "preferences.json is always written under --analyze.",
    )

    display = p.add_argument_group("display")
    display.add_argument("--top", type=int, default=10, metavar="N", help="rows in the report (default: 10)")
    display.add_argument(
        "--sort",
        default="enjoyment",
        choices=["enjoyment", "hours", "recent", "title"],
        help="report sort key (default: enjoyment)",
    )
    display.add_argument("--quiet", action="store_true", help="only print the final summary")
    display.add_argument("--silent", action="store_true", help="print nothing but errors")
    display.add_argument("--verbose", action="store_true", help="extra per-title detail")
    display.add_argument("--no-color", action="store_true", help="disable ANSI color")
    display.add_argument("--version", action="version", version=f"psnstats {__version__}")
    return p


def resolve_npsso(args) -> tuple[str | None, list[str]]:
    """Apply auth precedence: --npsso > --npsso-file (or default probe) > env.

    Returns ``(token, warnings)``. Warnings flag an over-permissive token file
    (group/world-readable) or one that exists but can't be read (instead of
    silently falling through to the env var and masking a permission typo).
    """
    warnings: list[str] = []
    if args.npsso:
        return args.npsso.strip(), warnings
    candidate = Path(args.npsso_file) if args.npsso_file else DEFAULT_CONFIG_NPSSO
    if candidate.exists():
        try:
            if candidate.stat().st_mode & 0o077:
                warnings.append(
                    f"NPSSO file {candidate} is group/world-readable; run: chmod 600 {candidate}"
                )
            return candidate.read_text(encoding="utf-8").strip(), warnings
        except OSError as exc:
            warnings.append(
                f"NPSSO file {candidate} exists but could not be read ({exc}); "
                "falling back to $PSN_NPSSO"
            )
    return (os.environ.get("PSN_NPSSO", "").strip() or None), warnings


def parse_platforms(raw: str) -> list[str]:
    items = [x.strip().lower() for x in raw.split(",") if x.strip()]
    bad = [x for x in items if x not in VALID_PLATFORMS]
    if bad:
        raise ValueError(f"invalid --platforms value(s): {', '.join(bad)} (choose from ps4,ps5,other)")
    return items or ["ps4", "ps5"]


def parse_formats(raw: str) -> set[str]:
    items = [x.strip().lower() for x in raw.split(",") if x.strip()]
    bad = [x for x in items if x not in VALID_FORMATS]
    if bad:
        raise ValueError(f"invalid --format value(s): {', '.join(bad)} (choose from csv,json,md,all)")
    if "all" in items:
        return {"csv", "json", "md"}
    return set(items) or {"csv", "json"}


def _main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    verbosity = 2
    if args.verbose:
        verbosity = 3
    if args.quiet:
        verbosity = 1
    if args.silent:
        verbosity = 0

    color_enabled = (
        not args.no_color and sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
    )
    c = Palette(color_enabled)

    def say(msg: str, level: int = 2):
        if verbosity >= level:
            print(msg)

    def err(msg: str):
        print(msg, file=sys.stderr)

    try:
        platforms = parse_platforms(args.platforms)
        formats = parse_formats(args.format)
    except ValueError as exc:
        err(c.red(f"error: {exc}"))
        return EXIT_FATAL

    # md is the analysis report, so requesting it implies --analyze.
    do_analyze = args.analyze or bool(args.compare) or "md" in formats

    if args.wishlist and args.user:
        err(c.red("error: --wishlist cannot combine with --user."))
        err("  Sony exposes no public wishlist; only your own account's wishlist is reachable.")
        return EXIT_FATAL

    npsso, npsso_warnings = resolve_npsso(args)
    for warning in npsso_warnings:
        say(c.yellow(f"warning: {warning}"), 1)
    if not npsso:
        err(c.red("error: no NPSSO token found."))
        err("  supply --npsso, --npsso-file PATH, or set $PSN_NPSSO")
        err(f"  get one at: {NPSSO_URL}")
        return EXIT_AUTH
    if len(npsso) < 50:
        say(c.yellow("warning: NPSSO token looks unusually short."), 1)

    if verbosity >= 2:
        say(c.dim("psnstats: NPSSO is only ever sent to Sony; it never leaves this machine."))

    # Authenticate.
    try:
        psnawp, client, my_id = authenticate(npsso)
    except AuthError:
        err(c.red("error: authentication failed. Your NPSSO token is likely expired (~60-day life)."))
        err(f"  get a fresh one at: {NPSSO_URL}")
        return EXIT_AUTH
    except Exception as exc:  # noqa: BLE001 - scrub the token before any surfaces
        # This is the only point the raw NPSSO is handed to third-party code, so
        # an *unexpected* error here is the one place its message could echo the
        # token back. Redact it before it can reach the terminal/logs/CI, then
        # re-raise for the top-level guard to report generically.
        raise RuntimeError(str(exc).replace(npsso, "<redacted-npsso>")) from None
    say(c.green(f"authenticated as {c.bold(my_id)}"), 1)

    # Resolve whose library.
    try:
        source, who = resolve_source(psnawp, client, args.user)
    except UserNotFoundError:
        err(c.red(f"error: PSN user not found: {args.user}"))
        return EXIT_FATAL
    if args.user:
        say(c.dim(f"target library: {who} (public titles only)"))

    # Fetch.
    def on_game(game):
        if verbosity >= 3:
            say(f"  [{game.system}] {game.title[:50]} — {game.playtime_hours:.1f}h", 3)

    say("fetching library...", 2)
    try:
        games, fetch_stats = fetch_title_stats(
            source, platforms, args.min_hours, args.limit, on_game=on_game
        )
    except ForbiddenError:
        err(c.red(f"error: {who}'s library is private."))
        return EXIT_FATAL

    if not games:
        err(c.yellow("no titles matched your filters (try --min-hours 0 or --platforms ps4,ps5,other)."))
        return EXIT_NOTHING

    say(
        c.dim(
            f"  fetched {fetch_stats['total_fetched']}, kept {fetch_stats['included']} "
            f"(skipped {fetch_stats['skipped_platform']} off-platform, "
            f"{fetch_stats['skipped_playtime']} under {args.min_hours:g}h)"
        ),
        2,
    )

    # Optional trophy enrichment.
    if args.trophies:
        say("fetching trophy completion (this is slower)...", 2)

        def on_prog(done, total):
            if verbosity >= 3:
                say(f"  trophies {done}/{total}", 3)

        enriched = enrich_trophies(source, games, on_progress=on_prog)
        say(c.dim(f"  enriched {enriched} titles with trophy data"), 2)

    outdir = Path(args.output)
    outdir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")

    written: list[str] = []

    if "json" in formats:
        json_path = outdir / f"psn_export_{date_str}.json"
        write_json(games, json_path)
        written.append(json_path.name)

    package = None
    if do_analyze:
        try:
            package = analyze_preferences(games, source_file=f"psn_export_{date_str}.json")
        except ValueError as exc:
            err(c.red(f"error: {exc}"))
            return EXIT_NOTHING

    # CSV: enriched analysis CSV when analyzing, else the base library CSV.
    if "csv" in formats:
        csv_path = outdir / f"psn_library_{date_str}.csv"
        if package is not None:
            write_analysis_csv(package["per_game_features"], csv_path)
        else:
            write_library_csv(games, csv_path)
        written.append(csv_path.name)

    if package is not None:
        prefs_path = outdir / "preferences.json"
        write_preferences(package, prefs_path)
        written.append(prefs_path.name)

        if "md" in formats:
            md_path = outdir / f"psn_report_{date_str}.md"
            md_path.write_text(
                render_markdown_report(package, top=args.top, sort=args.sort), encoding="utf-8"
            )
            written.append(md_path.name)

    # Wishlist export (own account; store products, not played titles, so it
    # gets its own files rather than rows in the library).
    wishlist_failed = False
    if args.wishlist:
        say("fetching store wishlist...", 2)
        try:
            wishlist = fetch_wishlist(psnawp)
        except WishlistUnavailableError as exc:
            err(c.red(f"error: wishlist unavailable: {exc}"))
            err("  the library export above still completed; if this persists, check for a")
            err("  newer psnstats (Sony rotates this undocumented query occasionally).")
            wishlist_failed = True
        else:
            say(c.dim(f"  {len(wishlist)} wishlist item(s)"), 2)
            # Stable, un-dated filenames (like preferences.json) so agents can
            # point at them across runs.
            if "csv" in formats:
                wl_csv = outdir / "wishlist.csv"
                write_wishlist_csv(wishlist, wl_csv)
                written.append(wl_csv.name)
            if "json" in formats:
                wl_json = outdir / "wishlist.json"
                write_wishlist_json(wishlist, wl_json)
                written.append(wl_json.name)

    say(c.green(f"wrote {len(written)} file(s) to {outdir}/ ({', '.join(written)})"), 1)

    # Report + compare to stdout.
    if package is not None and verbosity >= 2:
        say("")
        say(render_ascii_report(package, fetch_stats, top=args.top, sort=args.sort))

    if args.compare:
        old = _load_previous(args.compare, err, c)
        if old is None:
            return EXIT_FATAL
        delta = compare_packages(old, package)
        if verbosity >= 1:
            say("")
            say(render_compare(delta, top=args.top))

    # An explicitly requested wishlist that couldn't be fetched is a failure,
    # even though the library export completed (partial files stay on disk).
    if wishlist_failed:
        return EXIT_FATAL
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    """Top-level guard around the fetch/enrich/write pipeline.

    Known conditions (auth, missing user, private library, nothing matched) are
    handled with specific messages and exit codes inside ``_main``. Anything
    unexpected gets one clean error line and ``EXIT_FATAL`` instead of a raw
    traceback; the full traceback prints only under ``--verbose``.
    """
    raw_args = sys.argv[1:] if argv is None else argv
    try:
        return _main(argv)
    except KeyboardInterrupt:
        print("\naborted.", file=sys.stderr)
        return EXIT_FATAL
    except Exception as exc:  # noqa: BLE001 - deliberate top-level CLI guard
        print(f"error: unexpected failure ({type(exc).__name__}): {exc}", file=sys.stderr)
        if "--verbose" in raw_args:
            traceback.print_exc()
        return EXIT_FATAL


def _load_previous(path_str: str, err, c) -> dict | None:
    path = Path(path_str)
    if not path.exists():
        err(c.red(f"error: --compare file not found: {path_str}"))
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        err(c.red(f"error: could not read --compare file: {exc}"))
        return None
    if "per_game_features" not in data:
        err(c.red(f"error: --compare file is not a preferences.json (no per_game_features): {path_str}"))
        return None
    return data


if __name__ == "__main__":
    sys.exit(main())
