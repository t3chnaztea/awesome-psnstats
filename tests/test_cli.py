"""CLI-level tests: exception guard, npsso-file warnings, md-implies-analyze.

Network is monkeypatched away; no real psnawp calls.
"""

from __future__ import annotations

import argparse

from conftest import NOW
from psnstats import cli
from psnstats.analysis import Game


def _args(**over):
    base = {"npsso": None, "npsso_file": None}
    base.update(over)
    return argparse.Namespace(**base)


# --- item 4: npsso-file permission warnings ---


def test_resolve_npsso_warns_on_world_readable(tmp_path):
    f = tmp_path / "npsso"
    f.write_text("x" * 64)
    f.chmod(0o644)
    token, warnings = cli.resolve_npsso(_args(npsso_file=str(f)))
    assert token == "x" * 64
    assert any("group/world-readable" in w for w in warnings)


def test_resolve_npsso_no_warning_when_locked_down(tmp_path):
    f = tmp_path / "npsso"
    f.write_text("y" * 64)
    f.chmod(0o600)
    token, warnings = cli.resolve_npsso(_args(npsso_file=str(f)))
    assert token == "y" * 64
    assert warnings == []


def test_resolve_npsso_inline_takes_precedence(tmp_path):
    token, warnings = cli.resolve_npsso(_args(npsso="  inline  "))
    assert token == "inline"
    assert warnings == []


def test_resolve_npsso_env_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("PSN_NPSSO", "envtoken")
    # point the default probe at a nonexistent file
    monkeypatch.setattr(cli, "DEFAULT_CONFIG_NPSSO", tmp_path / "nope")
    token, warnings = cli.resolve_npsso(_args())
    assert token == "envtoken"
    assert warnings == []


# --- item 2: unexpected exceptions become one line + EXIT_FATAL ---


def test_main_catches_unexpected_exception(monkeypatch, capsys):
    def boom(argv):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(cli, "_main", boom)
    rc = cli.main([])
    assert rc == cli.EXIT_FATAL
    captured = capsys.readouterr()
    assert "unexpected failure" in captured.err
    assert "kaboom" in captured.err
    assert "Traceback" not in captured.err  # no raw traceback without --verbose


def test_main_verbose_prints_traceback(monkeypatch, capsys):
    def boom(argv):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(cli, "_main", boom)
    rc = cli.main(["--verbose"])
    assert rc == cli.EXIT_FATAL
    assert "Traceback" in capsys.readouterr().err


# --- item 5: --format md implies --analyze ---


def test_md_format_implies_analyze(monkeypatch, tmp_path):
    games = [
        Game("Elden Ring", "PPSA1_00", "PS5", 100.0, 300, NOW, 80),
        Game("Bloodborne", "CUSA1_00", "PS4", 40.0, 60, NOW, 90),
    ]

    monkeypatch.setattr(cli, "authenticate", lambda npsso: (object(), object(), "tester"))
    monkeypatch.setattr(cli, "resolve_source", lambda p, c, u: (object(), "tester"))
    monkeypatch.setattr(
        cli,
        "fetch_title_stats",
        lambda *a, **k: (games, {"total_fetched": 2, "included": 2,
                                 "skipped_platform": 0, "skipped_playtime": 0}),
    )

    rc = cli.main(
        ["--npsso", "z" * 64, "--format", "md", "--output", str(tmp_path), "--quiet"]
    )
    assert rc == cli.EXIT_OK
    # md alone triggered analysis: preferences.json + a markdown report exist,
    # and no csv/json were written.
    assert (tmp_path / "preferences.json").exists()
    assert list(tmp_path.glob("psn_report_*.md"))
    assert not list(tmp_path.glob("*.csv"))
    assert not list(tmp_path.glob("psn_export_*.json"))


# --- v1.1.0: --wishlist ---


def _patch_network(monkeypatch):
    games = [
        Game("Elden Ring", "PPSA1_00", "PS5", 100.0, 300, NOW, 80),
        Game("Bloodborne", "CUSA1_00", "PS4", 40.0, 60, NOW, 90),
    ]
    monkeypatch.setattr(cli, "authenticate", lambda npsso: (object(), object(), "tester"))
    monkeypatch.setattr(cli, "resolve_source", lambda p, c, u: (object(), "tester"))
    monkeypatch.setattr(
        cli,
        "fetch_title_stats",
        lambda *a, **k: (games, {"total_fetched": 2, "included": 2,
                                 "skipped_platform": 0, "skipped_playtime": 0}),
    )


def test_wishlist_conflicts_with_user(capsys):
    rc = cli.main(["--npsso", "z" * 64, "--wishlist", "--user", "someone"])
    assert rc == cli.EXIT_FATAL
    assert "--wishlist cannot combine with --user" in capsys.readouterr().err


def test_wishlist_writes_stable_files(monkeypatch, tmp_path):
    from psnstats.fetch import WishlistItem

    _patch_network(monkeypatch)
    monkeypatch.setattr(
        cli,
        "fetch_wishlist",
        lambda psnawp: [WishlistItem(name="Split Fiction", product_id="X", kind="Product")],
    )
    rc = cli.main(["--npsso", "z" * 64, "--wishlist", "--output", str(tmp_path), "--quiet"])
    assert rc == cli.EXIT_OK
    assert (tmp_path / "wishlist.csv").exists()
    assert (tmp_path / "wishlist.json").exists()


def test_wishlist_unavailable_is_fatal_but_library_still_written(monkeypatch, tmp_path, capsys):
    from psnstats.fetch import WishlistUnavailableError

    _patch_network(monkeypatch)

    def boom(psnawp):
        raise WishlistUnavailableError("PersistedQueryNotFound")

    monkeypatch.setattr(cli, "fetch_wishlist", boom)
    rc = cli.main(["--npsso", "z" * 64, "--wishlist", "--output", str(tmp_path), "--quiet"])
    assert rc == cli.EXIT_FATAL
    assert "wishlist unavailable" in capsys.readouterr().err
    # the library export completed before the wishlist failure
    assert list(tmp_path.glob("psn_library_*.csv"))
    assert not (tmp_path / "wishlist.csv").exists()
