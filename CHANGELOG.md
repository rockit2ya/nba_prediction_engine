# Changelog

All notable changes to the NBA Prediction Engine are documented in this file.

---

## [v3.2] — 2026-02-20 — Hardened Pipeline

A bug-fix and validation release focused on data integrity, team-name normalization, CLV accuracy, a new pre-flight validation system, and preflight audit stamping for bet trackers. These changes were discovered during paper-bet testing and collectively affect fair line calculations, CLV values, and injury/star-tax weighting for all downstream components.

### Added

#### `preflight_check.py` (NEW — 1,133 lines)

Pre-bet validation utility that audits the entire data pipeline before you place any bets. Designed as the safety net between `fetch_all_nba_data.sh` and `nba_engine_ui.py`.

- **59 checks across 12 sections:**

  | #   | Section                | Checks | What It Validates                                                                               |
  | --- | ---------------------- | ------ | ----------------------------------------------------------------------------------------------- |
  | 1   | Team Stats             | 7      | JSON parse, freshness, columns (PACE/ORtg/DRtg/NET/TEAM_NAME), 30 teams, ranges                 |
  | 2   | Injuries               | 5      | File exists, freshness, required columns, team count, canonical team names                      |
  | 3   | Star Tax               | 8      | JSON parse, freshness, 30 teams, valid IDs, no fetch errors, player count, ranges               |
  | 4   | Rest Penalties         | 6      | Freshness, parse, 30 teams, canonical names, penalty range (−4 to +4), B2B count                |
  | 5   | Odds                   | 4      | JSON parse, game count, spread variance & book coverage, freshness                              |
  | 6   | Schedule               | 5      | JSON parse, freshness, dates cached, today's games, canonical team names                        |
  | 7   | News                   | 4      | JSON parse, freshness, article count, title+summary structure                                   |
  | 8   | Bankroll Config        | 4      | JSON parse, starting_bankroll, unit_size, edge_cap                                              |
  | 9   | Cross-Data Consistency | 4      | Injury teams ⊂ stats, odds names canonical, schedule ⊂ odds, schedule ⊂ star tax                |
  | 10  | Model Spot-Check       | 5      | Runs `predict_nba_spread()` on up to 5 games; validates fair line, edge, Kelly                  |
  | 11  | Bet Tracker Integrity  | 4+     | Required columns, pick matches teams, numeric values, result/CLV sanity, preflight stamp status |
  | 12  | Pipeline Files         | 4      | 13 scripts present, `.env` API key, fetch script, static teams module                           |

- **Remediation guide:** Every `FAIL` includes a `fix=` hint. The summary prints a "HOW TO FIX" box with numbered steps and quick-fix tips. Warnings get a separate "WARNINGS TO REVIEW" box.
- **Usage modes:**
  - `python preflight_check.py` — full 59-check validation
  - `python preflight_check.py --quick` — data feeds + pipeline only (skip model & tracker)
  - `python preflight_check.py --fix` — auto re-run scrapers for stale/missing data, then validate
  - `python preflight_check.py --backfill` — add PreflightCheck/PreflightNote/ClosingLine/CLV columns to ALL historical trackers
- **Exit code:** Returns 1 if any FAIL, 0 if clean. Chainable: `python preflight_check.py && python nba_engine_ui.py`

#### Preflight Stamping & Audit Trail

Bet trackers now carry per-row `PreflightCheck` (timestamp) and `PreflightNote` (result summary) columns, providing a verifiable audit trail that data was validated before each bet.

- **Canonical header expanded:** 24 columns (added `ClosingLine`, `CLV`, `PreflightCheck`, `PreflightNote` to log_bet's header)
- **Auto-stamping on preflight pass:** When `preflight_check.py` succeeds (0 failures), all bets in today's tracker are stamped with the verification timestamp and note (e.g., `PASS (57✓ 3⚠)`)
- **Cross-script state:** `.preflight_status.json` saves the preflight result so `log_bet()` can auto-stamp new bets even before the tracker exists
- **Backfill mode:** `--backfill` retroactively adds the four columns to all historical trackers. Today's tracker gets a "run preflight to validate" note; past trackers get "Historical — cache data from {date} no longer available for retroactive validation"
- **Column reordering:** Backfill ensures canonical column order (`...ClosingLine,CLV,PreflightCheck,PreflightNote`) regardless of migration history
- **Format migration:** `log_bet()` handles 6 historical column formats (10→14→18→20→22→24 cols) with automatic padding
- **UI integration:** `nba_engine_ui.py` bet tracker display shows preflight verification summary (e.g., "✅ All 9 bet(s) verified" or "⚠️ 7/9 verified — 2 unstamped")
- **Idempotent:** Re-running preflight or backfill does not re-stamp already-handled rows

| File                 | Change                                                                                      |
| -------------------- | ------------------------------------------------------------------------------------------- |
| `nba_analytics.py`   | `log_bet()` header expanded to 24 cols; reads `.preflight_status.json` to auto-stamp bets   |
| `preflight_check.py` | Added `_stamp_tracker()`, `stamp_today_tracker()`, `backfill_trackers()`, `--backfill` flag |
| `update_results.py`  | Added `PreflightCheck`/`PreflightNote` column creation and string-type enforcement          |
| `nba_engine_ui.py`   | Bet tracker display shows preflight stamp summary per tracker                               |
| `.gitignore`         | Added `.preflight_status.json` (transient state file)                                       |

#### Bet Validation Audit (`[V]` command)

New `[V]` command in the engine UI audits ALL historical bet trackers for internal consistency. Since historical cache data is overwritten daily, predictions cannot be re-run — instead validates the recorded model outputs against known formulas.

- **Checks performed:** Edge math (`|Fair − Market|` with cap), Kelly formula, pick direction, edge-cap flags, preflight stamp coverage
- **Performance comparison:** Win rates for preflight-verified vs unverified bets
- **Per-file report:** Each tracker scored as Clean/Warn/Error with today's tracker marked 📌
- **Severity levels:** ERROR (math doesn't add up), WARN (data-quality concern), INFO (historical/override notes)
- **Kelly cap-awareness:** Correctly uses capped edge for Kelly verification on edge-capped bets

| File                 | Change                                                                          |
| -------------------- | ------------------------------------------------------------------------------- |
| `nba_engine_ui.py`   | Added `validate_historical_bets()` function and `[V]` menu command              |
| `preflight_check.py` | `check_bet_tracker()` now scans ALL trackers for conformance (not just today's) |

#### Scoreboard UX — Live Game Display & CLV Fetch Prompt

When ESPN replaces scheduled times with live scores mid-game, the scraper stored empty time strings and truncated team names (e.g. "LA" for Clippers, "Los Angeles" for Lakers). This caused blank status fields, "TBD" CLV labels for games already in progress, and a confusing "→ Run fetch" prompt even when odds were already fresh.

| File                  | Change                                                                                                                                                                                                                                        |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `schedule_scraper.py` | Added `"LA"` → Clippers and `"Los Angeles"` → Lakers to `CITY_TO_FULL`; added abbreviation fallback in `_parse_espn_next_data()`                                                                                                              |
| `nba_engine_ui.py`    | `load_schedule_for_date()` now normalizes names via `normalize_team()` and strips whitespace; empty status shows `⏳ Live`; CLV section shows "CLV locked (in progress)" for live games; fetch suggestion suppressed when odds are `✅ Fresh` |

### Fixed

#### Rest Penalty Scraper — Missing Teams

The rest penalty scraper only emitted teams found on ESPN's yesterday/today scoreboards. Teams that didn't play yesterday _and_ aren't playing today were completely absent from the cache, causing `rest.team_count` preflight failures on days with fewer games (e.g. 18/30 instead of 30/30).

| File                      | Change                                                                                                                                                            |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `rest_penalty_scraper.py` | After scraping yesterday/today scoreboards, backfill all 30 canonical teams from `SHORT_TO_FULL_TEAM` with `REST_PENALTY=0` for any team not on either scoreboard |

#### Star Tax — Outlier Impact Clamp (±15)

Low-minute / garbage-time players can have extreme on/off plus-minus values (e.g. Noa Essengue at -111.4). When such a player is injured ("Out for the season", weight=1.0), the unclamped value dominated the entire fair line calculation — producing absurd spreads like Chicago -62.98 vs Detroit.

| File               | Change                                                                                                                                                                                                                            |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `nba_analytics.py` | `get_star_tax_weighted()` now clamps each player's raw on/off impact to `±15` before applying the status weight. Elite stars rarely exceed ±12, so ±15 is a generous ceiling that filters noise while preserving real star impact |

#### Team Name Normalization — "LA Clippers" Catastrophe

The NBA.com stats API returns `"LA Clippers"` while every other data source uses `"Los Angeles Clippers"`. This inconsistency silently broke team lookups across 5 files, causing star tax, rest penalties, edge analysis, schedule matching, and post-mortem comparisons to silently fail for Clippers games.

| File                      | Change                                                                                                          |
| ------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `nba_analytics.py`        | Added `df['TEAM_NAME'].replace({'LA Clippers': 'Los Angeles Clippers'})` at cache load                          |
| `nba_analytics.py`        | Fixed `SHORT_TO_FULL` map: `'Clippers': 'Los Angeles Clippers'` (was `'LA Clippers'`)                           |
| `edge_analyzer.py`        | Fixed `SHORT_TO_FULL` map: `'Clippers': 'Los Angeles Clippers'` (was `'LA Clippers'`)                           |
| `rest_penalty_scraper.py` | Added aliases: `'LA Clippers': 'Los Angeles Clippers'`, `'LA Lakers': 'Los Angeles Lakers'`                     |
| `schedule_scraper.py`     | Fixed `CITY_TO_FULL` map: replaced ambiguous `'LA'` key with explicit `'LA Clippers'` and `'LA Lakers'` entries |
| `post_mortem.py`          | Added alias: `'la clippers': 'los angeles clippers'` to `TEAM_ALIASES`                                          |

#### CLV (Closing Line Value) — Sign Convention Fix

CLV was always calculated as `closing - market`, which is correct for AWAY picks but inverted for HOME picks. A bettor taking HOME -5.5 who sees the line close at -7.0 should have _positive_ CLV (they got fewer points to give), but the old formula returned negative.

| File                | Change                                                                                                                 |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `update_results.py` | CLV now uses bettor-perspective sign: `raw_clv = closing - market`, then `clv = -raw_clv if pick == home else raw_clv` |
| `update_results.py` | Added pre-pass: CLV is populated for PENDING bets as soon as closing odds are cached (before game finishes)            |

#### Injury Scraper — Complete Rewrite

The original single-table parser broke when CBS Sports changed their layout to per-team sections. The scraper was silently returning 0 injuries.

| File                | Change                                                                                                                  |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `injury_scraper.py` | Rewrote to iterate per-team sections (`TeamName` header + `TableBase-table`)                                            |
| `injury_scraper.py` | Added `CBS_TEAM_MAP` with 35 city-to-full-name aliases (handles `"L.A. Clippers"`, `"Golden St."`, `"Okla City"`, etc.) |
| `injury_scraper.py` | Added `_clean_player_name()` fallback for concatenated abbreviated+full names                                           |
| `injury_scraper.py` | Added `User-Agent` header and timeout to `requests.get()`                                                               |
| `injury_scraper.py` | Added `date` column (update date from CBS) to output CSV                                                                |

#### Star Tax — Status Matching

The star tax weighting function was doing exact string matching against injury statuses, missing common values.

| File               | Change                                                                             |
| ------------------ | ---------------------------------------------------------------------------------- |
| `nba_analytics.py` | Added `'game time decision': 0.5` and `'day-to-day': 0.5` to injury status weights |
| `nba_analytics.py` | Status matching is now case-insensitive (`p_info['status'].lower()`)               |
| `nba_analytics.py` | Team ID lookup uses `str(int(team_id))` to handle float TEAM_IDs from DataFrame    |

#### Injury Flagging — Case-Insensitive + Season-Long OUT

| File               | Change                                                                               |
| ------------------ | ------------------------------------------------------------------------------------ |
| `nba_analytics.py` | Injury status comparisons now use `.lower()` throughout `predict_nba_spread()`       |
| `nba_analytics.py` | Added `'out for the season'` to the flagged status list                              |
| `nba_analytics.py` | Date check relaxed: flags player if no date field set (catches season-long injuries) |

#### Odds API — Full Name Matching

| File          | Change                                                                                                                    |
| ------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `odds_api.py` | `get_closing_line()` now accepts full team names (e.g., `"Cleveland Cavaliers"`) in addition to nicknames (`"Cavaliers"`) |
| `odds_api.py` | Matching checks both `away`/`home` (nickname) and `away_full`/`home_full` (full name) fields                              |

### Impact Assessment

These fixes collectively affected:

- **Fair line calculations** — star tax and rest penalties were silently returning 0 for Clippers games, and status mismatches caused other teams' star impacts to be underweighted.
- **CLV values** — all HOME-side bets had inverted CLV signs. Pre-existing bet trackers needed recalculation.
- **Injury data** — the broken single-table parser was returning 0 injuries, causing the model to ignore all injury impacts.
- **Cross-file consistency** — 5 files had independent team-name maps that disagreed on Clippers naming.

---

## [v3.1] — Cache-Only Architecture

Ground-up reliability and performance overhaul. The engine now runs entirely off pre-cached data — zero live API calls from the UI.

### Changed

- Replaced all `nba_api` calls with direct web scraping (Selenium for NBA.com, ESPN JSON API for scores)
- Added `nba_teams_static.py` — local static module with all 30 NBA teams (zero network dependency)
- Added `schedule_prefetch.py` — ESPN schedule prefetcher
- Added `star_tax_prefetch.py` — NBA.com player NET_RATING Selenium scraper
- Added `fetch_all_nba_data.sh` — master pipeline script (8 prefetchers, 6 cache validations)
- UI startup reduced from 30+ seconds to < 1 second
- Removed `nba_api` dependency entirely

### Added

- Stale cache warnings with configurable threshold (`STALE_HOURS` in `.env`)
- Upcoming games browser (`[U]` command — 7-day lookahead, preview mode)
- Bet tracker viewer (`[B]` command — formatted table with P&L summary)
- Pre-tipoff review (`[P]` command — injury changes, line movement, HOLD/REVIEW/HEDGE actions)
- CLV tracking via The Odds API (`odds_api.py` + `update_results.py`)
- Per-window CLV freshness on game dashboard
- Edge cap system with audit in Lifetime Dashboard
- Real-money P&L tracking (sportsbook, odds, bet amount, ToWin, Payout)
- `text_to_image.py` — terminal output → PNG screenshot renderer
