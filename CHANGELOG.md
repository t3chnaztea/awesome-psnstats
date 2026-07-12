# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
