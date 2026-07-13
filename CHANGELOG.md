# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security
- CSV exports now neutralize formula injection: any `title`/`name` cell that
  starts with a spreadsheet formula trigger (`= + - @` or tab/CR) is prefixed
  with `'` so a crafted game title or wishlist name can't execute as a formula
  when the file is opened in Excel/Sheets.
- Redact the NPSSO token from any unexpected error surfaced during
  authentication, so it can never echo back to the terminal, shell logs, or CI.

## [1.1.1] - 2026-07-12

Docs-only release; no code changes.

### Changed
- README rewritten in a plain, instructional style modeled on psnawp's:
  install, getting started with the npsso steps and a worked example, then
  reference sections. Competitive positioning removed; a Credit section
  (psnawp, andshrew's endpoint documentation) added. This refreshes the
  PyPI project page.

[1.1.1]: https://github.com/t3chnaztea/awesome-psnstats/releases/tag/v1.1.1

## [1.1.0] - 2026-07-12

### Added
- `--wishlist`: export your store wishlist to `wishlist.csv` / `wishlist.json`
  (stable, un-dated filenames, like `preferences.json`). Own account only;
  Sony exposes no public wishlist, so it cannot combine with `--user`. Items
  carry name, product id, kind (Product vs pre-release Concept), platforms,
  edition classification, current base/discounted price with sale text, and
  box art URL.
- A wishlist-ranking starter prompt in the README: hand `wishlist.json` plus
  `preferences.json` to an LLM and get the wishlist ranked against how you
  actually play.

### Notes
- The wishlist endpoint is an undocumented persisted GraphQL query (the one
  the PS App uses). If Sony rotates it, `--wishlist` fails with a clear error
  and exit `1`; the library export still completes first.

[1.1.0]: https://github.com/t3chnaztea/awesome-psnstats/releases/tag/v1.1.0

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
