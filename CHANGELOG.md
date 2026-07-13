# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.1] - 2026-07-12

Hardening pass from a post-ship review. No behavior change to a normal run.

### Added
- `--format md` now implies `--analyze` instead of silently writing nothing.
- Warning when the NPSSO token file is group/world-readable, and a distinct
  message when it exists but can't be read (no longer silently ignored).

### Changed
- Unexpected errors now print one clean line and exit `1` instead of dumping a
  raw traceback; the full traceback prints only with `--verbose`.
- `--npsso` help and the README security section note that inline tokens land
  in shell history and `ps` output; prefer `--npsso-file` or `$PSN_NPSSO`.
- Release workflow publishes to PyPI via Trusted Publishing (OIDC) again, with
  least-privilege `permissions` blocks; no stored PyPI token.

[1.0.1]: https://github.com/t3chnaztea/awesome-psnstats/releases/tag/v1.0.1

## [1.0.0] - 2026-07-12

Initial public release.

### Added
- Export PS4/PS5 play history (playtime, play count, last played) to CSV and JSON.
- `--analyze`: per-game enjoyment scoring, five player traits, and a stable
  `preferences.json` taste profile with an `agent_features` block for AI agents.
- `--trophies`: optional trophy-completion enrichment (fills completion and
  abandonment signals).
- `--compare PATH`: diff a run against a previous `preferences.json`
  (new titles, hours gained, trait drift).
- `--user`, `--platforms`, `--min-hours`, `--limit`, `--top`, `--sort`,
  `--format csv,json,md,all`, and verbosity/color controls.
- Markdown and ASCII reports; NPSSO auth via flag, file, or environment variable.
- Meaningful exit codes: `0` ok, `1` fatal, `2` auth, `3` nothing matched.

[1.0.0]: https://github.com/t3chnaztea/awesome-psnstats/releases/tag/v1.0.0
