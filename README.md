# psnstats

Export your PS4/PS5 play history from the PlayStation Network to CSV/JSON, and optionally build an LLM-ready taste profile (with prompts), entirely on your machine.

[![PyPI](https://img.shields.io/pypi/v/awesome-psnstats.svg)](https://pypi.org/project/awesome-psnstats/)
[![Python versions](https://img.shields.io/pypi/pyversions/awesome-psnstats.svg)](https://pypi.org/project/awesome-psnstats/)
[![CI](https://github.com/t3chnaztea/awesome-psnstats/actions/workflows/ci.yml/badge.svg)](https://github.com/t3chnaztea/awesome-psnstats/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

`psnstats` is an end-user command-line tool, not an API wrapper. It fetches every PS4/PS5 title you have played (playtime, play counts, last played), writes them to files you own, and can layer on trophy completion, a taste-analysis profile for LLM use, a run-to-run diff, and a store wishlist export. It deliberately skips PSN's social surface (friends, presence, messaging, search); if you need those, use [psnawp](https://github.com/isFakeAccount/psnawp) directly, which this tool is built on.

## How to install

### From PyPI

```
pipx install awesome-psnstats
```

(or `pip install awesome-psnstats`). The console command is `psnstats`.

## Getting Started

> [!CAUTION]
> This tool uses an unofficial, reverse-engineered PlayStation Network API (via the `psnawp` library, which self rate limits at 300 requests per 15 minutes). Normal, occasional runs are low-risk, but excessive use may lead to your PSN account being temporarily or permanently banned. Your NPSSO token is a session cookie equivalent to your password: `psnstats` sends it only to Sony's own API endpoints, and nothing else leaves your machine.

To get started you need to obtain your npsso (64 character code):

1. Log in to your [PlayStation](https://www.playstation.com/) account in your browser.
2. In another tab of the same browser, go to `https://ca.account.sony.com/api/v1/ssocookie`.
3. If you are logged in you should see a text similar to this:

```json
{"npsso":"<64 character npsso code>"}
```

The npsso expires after about 60 days; get a fresh one when authentication starts failing.

Following is a quick example of how to use this tool:

```bash
export PSN_NPSSO="<64 character npsso code>"

# Base export: library CSV + JSON into ./psn-export/
psnstats

# Add the taste profile (preferences.json, traits, report)
psnstats --analyze

# Enrich with trophy completion, and also export your store wishlist
psnstats --analyze --trophies --wishlist

# Diff against a previous run
psnstats --analyze --compare ./psn-export/preferences.json

# Another account's public library
psnstats --user VaultTec-Co
```

A run with `--analyze` prints a report like this (synthetic data from [examples/](examples/)):

```
----------------------------------------------------------------------
TOP 10 GAMES (by enjoyment)
----------------------------------------------------------------------
#   Title                          Sys  Score  Hrs   Plays  Last
----------------------------------------------------------------------
1   Elden Ring                     PS5  91.2   120   340    2026-07
2   Bloodborne                     PS4  79.2   62    90     2026-05
3   Stardew Valley                 PS4  79.0   90    180    2026-06
...

----------------------------------------------------------------------
PLAYER TRAITS
----------------------------------------------------------------------
Snackable      [##############------]  71.4  (sessions/hr: 2.10 median)
Marathon       [############--------]  64.3  (hrs/session: 0.5 median)
Completionist  [##########----------]  50.0  (completion: 58% avg)
Friction Tol   [###-----------------]  17.9  (early: 14%, late: 29%)
Variety        [###################-]  95.0  (entropy: 1.00)
```

## How the analysis works

With `--analyze`, every game gets an enjoyment score (0-100), a weighted blend of four signals:

```
enjoyment = 0.35 * playtime (log-scaled)
          + 0.25 * recency  (90-day half-life decay)
          + 0.20 * completion (neutral 50 without --trophies)
          + 0.20 * replay    (play count + long-session bonuses)
```

Two abandonment penalties then apply: -15 if you bounced early (under 20% complete after 3+ sessions) and -10 if you stalled late (10+ hours in, under 40% complete). Completion signals require `--trophies`; without it, completion goes neutral.

From the per-game scores it derives five player traits (each 0-100): snackable (short, frequent bursts), marathon (long single sittings), completionist (how far into games you push), friction tolerance (whether you stick with hard/slow games or drop them), and variety (spread across platforms and kinds of games).

`preferences.json` also carries an `agent_features` block: session style, commitment style, platform recency split, plain-language positive/avoid signals, and the exact weights and thresholds used, so an LLM can reason about why a score is what it is.

## Example prompts

`preferences.json` is written to be pasted straight into a chat with an LLM:

**Get recommendations:**

> Here is my PlayStation taste profile as JSON. Based on the traits, enjoyment scores, and positive/avoid signals, recommend 5 games I haven't played that fit how I actually play, and for each, say which signal it matches.
>
> ```json
> { ...paste the contents of preferences.json... }
> ```

**Triage your backlog** (paste `library.csv` too):

> Here are my taste profile and full play history. Which games I started but didn't finish are worth going back to, and which should I officially drop? Use my friction tolerance and abandonment signals to justify each call.

**Buy advice:**

> Here is my taste profile. I'm considering buying <game>. Predict how likely I am to actually finish and enjoy it, citing the specific traits and signals that support the prediction. Be honest if it matches my avoid signals.

**Rank your wishlist** (run with `--wishlist`, paste `wishlist.json` too):

> Here are my taste profile and my store wishlist. Rank the wishlist by how likely I am to actually play and finish each game, not by hype. Flag anything that matches my avoid signals, and tell me which one to buy next and which to quietly remove.

`preferences.json` and the wishlist files keep stable, un-dated names, so you can point a tool or agent at them and re-run monthly to keep them fresh.

## Output files

Everything goes to `./psn-export/` (change with `--output`):

- `psn_library_<date>.csv`: the per-game export (see schema below)
- `psn_export_<date>.json`: the same data as JSON
- `preferences.json`: the taste profile (`--analyze`; stable filename)
- `psn_report_<date>.md`: the report as markdown (`--format md`)
- `wishlist.csv` / `wishlist.json`: your store wishlist (`--wishlist`; stable filenames) with name, edition, platforms, and current base/discounted price

With `--analyze`, `psn_library_<date>.csv` has 12 columns:

| Column | Meaning |
| --- | --- |
| `title` | Game name |
| `system` | `PS4` / `PS5` / `OTHER` |
| `playtime_hours` | Total hours played (float) |
| `play_count` | Number of sessions |
| `last_played` | Date last played (`YYYY-MM-DD`) |
| `enjoyment_score` | 0-100 blended score |
| `completion_ratio` | 0-1 trophy completion (blank without `--trophies`) |
| `recency_days` | Days since last played |
| `hours_per_session` | Marathon signal |
| `sessions_per_hour` | Snackability signal |
| `early_abandon` | Bounced early (bool) |
| `late_abandon` | Stalled late (bool) |

Without `--analyze`, the CSV is a leaner base export (title, ids, playtime, plays, last played).

## Flag reference

**Authentication** (precedence: `--npsso` > `--npsso-file` > `$PSN_NPSSO`)
- `--npsso TOKEN`: pass the token inline
- `--npsso-file PATH`: read from a file (default probe: `~/.config/psnstats/npsso`; `chmod 600` it)

**Scope**
- `--user ONLINE_ID`: export another account's *public* library instead of your own
- `--platforms LIST`: comma list of `ps4,ps5,other` (default `ps4,ps5`)
- `--min-hours N`: skip titles under N hours (default `1`; use `0` for a full dump)
- `--limit N`: stop after N kept titles (handy for a quick test)
- `--wishlist`: also export your store wishlist (own account only; can't combine with `--user`)

**Enrichment**
- `--trophies`: fetch trophy completion (fills completion + abandonment; adds ~80 requests on a 400-game library)

**Analysis**
- `--analyze`: compute the taste profile (default: off)
- `--compare PATH`: diff this run against a previous `preferences.json` (implies `--analyze`)

**Output**
- `--output DIR`: output directory (default `./psn-export`)
- `--format LIST`: comma list of `csv,json,md,all` (default `csv,json`); `md` is the report and implies `--analyze`

**Display**
- `--top N`, `--sort enjoyment|hours|recent|title`, `--quiet`, `--silent`, `--verbose`, `--no-color`, `--version`

**Exit codes:** `0` ok · `1` fatal · `2` auth · `3` nothing matched.

## About your NPSSO token

- An NPSSO is a session cookie. Treat it like a password: anyone with it can act as you on PSN.
- It expires after ~60 days; regenerate it when auth starts failing.
- `psnstats` sends it only to Sony's own API endpoints, never to any third party.
- Prefer a file over an env var for long-term use, and lock it down: `chmod 600 ~/.config/psnstats/npsso`. `psnstats` warns if the file is group/world-readable.
- Avoid the inline `--npsso` flag except for a quick test: it lands in your shell history and is visible in `ps` output. Use `--npsso-file` or `$PSN_NPSSO` instead.

## FAQ

**Can I export PS3 or Vita playtime?** No. Sony's API does not expose playtime for PS3/Vita titles, so no tool can.

**Will this get my account banned?** It uses the same unofficial API as other community tools, plus `psnawp`'s built-in rate limiting (300 req / 15 min). Normal, occasional runs are low-risk, but there is no official guarantee. Don't hammer it.

**Can I export a friend's library?** Only their public titles, via `--user THEIR_ONLINE_ID`, and only if their privacy settings allow it.

**Can I export my wishlist?** Yes: `--wishlist` writes `wishlist.csv`/`wishlist.json` with name, edition, platforms, and current price/discount (your own account only; Sony exposes no public wishlist). There is no documented wishlist API, so this rides the same persisted GraphQL query the PS App uses. If Sony rotates it, the flag fails with a clear error until psnstats updates the query.

## Roadmap

- Purchased-games list, for an "owned but never played" backlog report
- Genre/metadata enrichment (external catalog join)
- A Steam adapter reusing the same pure analysis engine
- `stdout` streaming for piping into other tools

## Contribution

Bug reports, feature requests, and PRs are all welcome. Dev setup:

```bash
git clone https://github.com/t3chnaztea/awesome-psnstats
cd awesome-psnstats
pip install -e ".[dev]"
ruff check . && pytest
```

## Disclaimer

This project was not intended to be used for spam, abuse, or anything of the sort, and no such use is endorsed. `psnstats` is an unofficial tool, not affiliated with, endorsed by, or supported by Sony Interactive Entertainment. "PlayStation", "PS4", and "PS5" are trademarks of Sony Interactive Entertainment Inc.

## Credit

Built on the excellent [psnawp](https://github.com/isFakeAccount/psnawp) library, which handles authentication, rate limiting, and the title-stats and trophy endpoints. Special thanks to [@andshrew](https://github.com/andshrew/PlayStation-Trophies) for documenting the PlayStation API endpoints, including the wishlist query this tool uses.

## License

[MIT](LICENSE)
