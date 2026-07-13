# psnstats

**Export your PlayStation Network play history to CSV/JSON and build an LLM-ready taste profile (with prompts), entirely on your machine.**

[![PyPI](https://img.shields.io/pypi/v/awesome-psnstats.svg)](https://pypi.org/project/awesome-psnstats/)
[![Python versions](https://img.shields.io/pypi/pyversions/awesome-psnstats.svg)](https://pypi.org/project/awesome-psnstats/)
[![CI](https://github.com/t3chnaztea/awesome-psnstats/actions/workflows/ci.yml/badge.svg)](https://github.com/t3chnaztea/awesome-psnstats/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

`psnstats` pulls every PS4/PS5 title you've played, with real playtime and play counts, into plain `.csv` and `.json` files you own. Add `--analyze` and it also scores each game, derives five player traits, and writes a `preferences.json` you can hand to an LLM to get recommendations that actually fit how you play.

Your NPSSO session token is only ever sent to Sony. Nothing else leaves your machine.

## What it looks like

```
======================================================================
ANALYSIS REPORT
======================================================================

fetch ok   : 131 games from API
export ok  : 14 games kept
             (skipped 3 off-platform, 114 under threshold)
analyze ok : 14 games

----------------------------------------------------------------------
TOP 10 GAMES (by enjoyment)
----------------------------------------------------------------------
#   Title                          Sys  Score  Hrs   Plays  Last
----------------------------------------------------------------------
1   Elden Ring                     PS5  91.2   120   340    2026-07
2   Bloodborne                     PS4  79.2   62    90     2026-05
3   Stardew Valley                 PS4  79.0   90    180    2026-06
4   God of War Ragnarok            PS5  76.9   45    60     2026-06
5   Cyberpunk 2077                 PS5  74.5   80    110    2026-05
6   Hades                          PS5  73.2   38    210    2026-07
7   Disco Elysium - The Final Cut  PS5  71.3   24    20     2026-06
8   Returnal                       PS5  65.0   30    75     2026-06
9   Tetris Effect                  PS4  60.4   12    140    2026-07
10  Untitled Goose Game            PS4  58.0   6     12     2026-05

----------------------------------------------------------------------
PLAYER TRAITS
----------------------------------------------------------------------
Snackable      [##############------]  71.4  (sessions/hr: 2.10 median)
Marathon       [############--------]  64.3  (hrs/session: 0.5 median)
Completionist  [##########----------]  50.0  (completion: 58% avg)
Friction Tol   [###-----------------]  17.9  (early: 14%, late: 29%)
Variety        [###################-]  95.0  (entropy: 1.00)

----------------------------------------------------------------------
PLAY STYLE
----------------------------------------------------------------------
Session style      : mixed
Commitment style   : mixed
Platform recency   : PS5 66% / PS4 34%
```

(Example above is [synthetic data](examples/); your own run reflects your library.)

## Why

The most-starred "PSN API" projects — [psn-api](https://github.com/achievements-app/psn-api), [psn-php](https://github.com/Tustin/psn-php), and [psnawp](https://github.com/isFakeAccount/psnawp) (which this is built on) — are **developer libraries**: they hand you raw endpoints, not files. The only end-user *tools* scrape a third-party website. Nothing shipped turns your library into files you own, and nothing anywhere computes a taste profile from it.

**`psnstats` is the first end-user tool on Sony's own API with playtime export, multi-format output, delta compare, and a taste-analysis layer.**

- **You own the files.** [Exophase](https://www.exophase.com/) and [PSNProfiles](https://psnprofiles.com/) show your stats on *their* website. `psnstats` gives you `.csv` and `.json` on disk to keep, diff, and feed to other tools.
- **Playtime *and* taste.** Plenty of scrapers can list your trophies. Nothing else turns your actual playtime into an enjoyment model and a portable taste profile for an LLM.
- **Local-first.** No account, no server, no telemetry. Your NPSSO token is sent only to Sony's own API.

It deliberately skips the social surface (friends, presence, messaging, search) — that's what the libraries are for. This is a tool, not a wrapper.

## Quickstart

Install with [pipx](https://pipx.pypa.io/) (isolated) or pip:

```bash
pipx install awesome-psnstats     # console command is: psnstats
```

Get your NPSSO token (a session cookie):

1. Log in to [playstation.com](https://www.playstation.com/) in your browser.
2. In the same browser, open <https://ca.account.sony.com/api/v1/ssocookie>.
3. Copy the 64-character `npsso` value from the JSON.

Run it:

```bash
export PSN_NPSSO="paste_your_token_here"
psnstats --analyze
```

That writes `./psn-export/` with your library CSV, a JSON export, and `preferences.json`.

## The taste model

With `--analyze`, every game gets an **enjoyment score** (0-100), a weighted blend of four signals:

```
enjoyment = 0.35 * playtime (log-scaled)
          + 0.25 * recency  (90-day half-life decay)
          + 0.20 * completion (neutral 50 without --trophies)
          + 0.20 * replay    (play count + long-session bonuses)
```

Two abandonment penalties then apply: **-15** if you bounced early (under 20% complete after 3+ sessions) and **-10** if you stalled late (10+ hours in, under 40% complete). Completion signals require `--trophies`; without it, completion goes neutral.

From the per-game scores it derives **five player traits** (each 0-100):

- **Snackable** — do you play in short, frequent bursts?
- **Marathon** — or long single sittings?
- **Completionist** — how far into games do you push?
- **Friction tolerance** — do you stick with hard/slow games or drop them?
- **Variety** — how spread across platforms/kinds of games are you?

And an **`agent_features`** block: a preferred session style, commitment style, platform recency split, and plain-language positive/avoid signals — plus the exact weights and thresholds used, so an LLM can reason about *why*.

### The prompts

`preferences.json` is designed to be pasted straight into a chat with an LLM. Three starters:

**Get recommendations:**

> Here is my PlayStation taste profile as JSON. Based on the traits, enjoyment scores, and positive/avoid signals, recommend 5 games I haven't played that fit how I actually play — and for each, say which signal it matches.
>
> ```json
> { ...paste the contents of preferences.json... }
> ```

**Triage your backlog** (paste `library.csv` too):

> Here are my taste profile and full play history. Which games I started but didn't finish are worth going back to, and which should I officially drop? Use my friction tolerance and abandonment signals to justify each call.

**Buy advice:**

> Here is my taste profile. I'm considering buying <game>. Predict how likely I am to actually finish and enjoy it, citing the specific traits and signals that support the prediction. Be honest if it matches my avoid signals.

The filename stays stable (never dated), so you can point a tool or agent at `./psn-export/preferences.json` and re-run monthly to keep it fresh.

## CSV schema

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

Without `--analyze`, you get a leaner base library CSV (title, ids, playtime, plays, last played).

## Flag reference

**Authentication** (precedence: `--npsso` > `--npsso-file` > `$PSN_NPSSO`)
- `--npsso TOKEN` — pass the token inline
- `--npsso-file PATH` — read from a file (default probe: `~/.config/psnstats/npsso`; `chmod 600` it)

**Scope**
- `--user ONLINE_ID` — export another account's *public* library instead of your own
- `--platforms LIST` — comma list of `ps4,ps5,other` (default `ps4,ps5`)
- `--min-hours N` — skip titles under N hours (default `1`; use `0` for a full dump)
- `--limit N` — stop after N kept titles (handy for a quick test)

**Enrichment**
- `--trophies` — fetch trophy completion (fills completion + abandonment; adds ~80 requests on a 400-game library)

**Analysis**
- `--analyze` — compute the taste profile (default: off)
- `--compare PATH` — diff this run against a previous `preferences.json` (implies `--analyze`)

**Output**
- `--output DIR` — output directory (default `./psn-export`)
- `--format LIST` — comma list of `csv,json,md,all` (default `csv,json`); `md` is a markdown report

**Display**
- `--top N`, `--sort enjoyment|hours|recent|title`, `--quiet`, `--silent`, `--verbose`, `--no-color`, `--version`

**Exit codes:** `0` ok · `1` fatal · `2` auth · `3` nothing matched.

## About your NPSSO token

- An NPSSO is a **session cookie**. Treat it like a password: anyone with it can act as you on PSN.
- It **expires after ~60 days**; regenerate it when auth starts failing.
- `psnstats` sends it **only to Sony's own API endpoints** — never to any third party.
- Prefer a file over an env var for long-term use, and lock it down: `chmod 600 ~/.config/psnstats/npsso`. `psnstats` warns if the file is group/world-readable.
- Avoid the inline `--npsso` flag except for a quick test: it lands in your shell history and is visible in `ps` output. Use `--npsso-file` or `$PSN_NPSSO` instead.

## FAQ

**Can I export PS3 or Vita playtime?** No. Sony's API simply does not expose playtime for PS3/Vita titles, so no tool can.

**Will this get my account banned?** It uses the same unofficial API as other community tools, plus `psnawp`'s built-in rate limiting (300 req / 15 min). Normal, occasional runs are low-risk, but there is no official guarantee. Don't hammer it.

**Can I export a friend's library?** Only their **public** titles, via `--user THEIR_ONLINE_ID`, and only if their privacy settings allow it.

**Can I export my wishlist?** No public endpoint exists for wishlists.

## Roadmap

- Purchased-games list → an "owned but never played" backlog report
- Genre/metadata enrichment (external catalog join)
- A Steam adapter reusing the same pure analysis engine
- `stdout` streaming for piping into other tools

## Contributing

Issues and PRs welcome. Dev setup:

```bash
git clone https://github.com/t3chnaztea/awesome-psnstats
cd awesome-psnstats
pip install -e ".[dev]"
ruff check . && pytest
```

## Disclaimer

`psnstats` is an unofficial tool. It is not affiliated with, endorsed by, or supported by Sony Interactive Entertainment. "PlayStation", "PS4", and "PS5" are trademarks of Sony Interactive Entertainment Inc. Built on the excellent [psnawp](https://github.com/isFakeAccount/psnawp) library.

## License

[MIT](LICENSE)
