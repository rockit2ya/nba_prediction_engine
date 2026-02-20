# 🏀 NBA Predictive Analytics Engine (v3.1 — Cache-Only Architecture)

This README covers the features, technical architecture, mathematical modeling, and deployment steps for the NBA Prediction Engine (engine).

### **Overview**

The **NBA Pro Engine (V3.1)** is a situational analytics tool designed for high-fidelity point spread predictions. Unlike basic models that use season averages, this engine prioritizes "Current Form" and "Immediate Context" to find market inefficiencies. It leverages the **NBA's Four-Factors** and advanced efficiency ratings to calculate a "Fair Line" (Projected Spread) for daily matchups.

**v3.1** is a ground-up reliability and performance overhaul. The engine now runs entirely off pre-cached data — **zero live API calls** are made from the UI. All data is fetched by dedicated prefetch scripts (`fetch_all_nba_data.sh`), and the UI reads only from local cache files. This eliminates API timeouts, rate limits, and network dependency during analysis, cutting startup time from **30+ seconds to under 1 second**.

### **What Changed in v3.1**

| Area             | Before (v3.0)                                 | After (v3.1)                                                  |
| ---------------- | --------------------------------------------- | ------------------------------------------------------------- |
| **Schedule**     | Live `ScoreboardV2` API call on every startup | Pre-cached from ESPN via `schedule_prefetch.py`               |
| **Team Stats**   | `nba_api` Python module (frequent timeouts)   | Selenium scrape of NBA.com, cached to JSON                    |
| **Star Tax**     | Live `nba_api` player on/off stats            | Pre-cached NET_RATING from NBA.com via `star_tax_prefetch.py` |
| **Final Scores** | `nba_api` ScoreboardV2 endpoint               | ESPN JSON API (`site.api.espn.com`)                           |
| **Team Lookups** | `nba_api.stats.static` (network import)       | Local `nba_teams_static.py` module (zero I/O)                 |
| **UI Startup**   | 30+ seconds (API calls + retries)             | < 1 second (cache reads only)                                 |
| **Failure Mode** | Crashes or hangs on API timeout               | Always works if caches exist; stale-data warnings shown       |
| **Dependencies** | `nba_api==1.11.3` required                    | `nba_api` fully removed                                       |

> **Why `nba_api` was removed:** The `nba_api` Python module (which wraps `stats.nba.com` endpoints) proved chronically unreliable — requests would frequently timeout, hang indefinitely, or get rate-limited with no error message. This caused the UI to stall for 30+ seconds on startup and sometimes crash entirely. Rather than continuing to work around an unstable dependency, v3.1 replaced every `nba_api` call with direct web scraping (Selenium for NBA.com advanced stats, ESPN JSON API for schedule and scores) and a local static team-data module (`nba_teams_static.py`). The result is faster, more reliable, and fully offline once caches are populated.

### **Key Pro Features**

- **Cache-Only Architecture:** The UI makes zero network calls. All data is pre-fetched by `fetch_all_nba_data.sh` and read from local cache files. Startup is sub-second.
- **Stale Cache Warnings:** The banner shows cache freshness with feed source labels. Caches older than 12 hours (configurable via `STALE_HOURS` in `.env`) are flagged with a warning.
- **Multi-Source Data Pipeline:** ESPN (schedule, scores, news, rest), NBA.com (team advanced stats, player NET_RATING), CBS Sports (injuries), The Odds API (spreads/CLV).
- **Situational Modeling:** Factors in Back-to-Back (B2B) fatigue and dynamic Home Court Advantage (HCA).
- **Bayesian Star Tax:** Uses individual NET_RATING metrics weighted by official injury status (OUT, GTD, Doubtful).
- **Upcoming Games Browser:** `[U]` command displays the next 7 days of NBA games with selectable game IDs for pre-game research. Upcoming games run in **preview mode** (no bet logging) to encourage re-analysis with fresh data on game day. After each analysis, the upcoming list redisplays so you can analyze another game. Press `Q` to return to the main menu.
- **Bet Tracker Viewer:** `[B]` command displays a formatted table of all bets from any tracker file (or all combined), with per-bet details and a P&L summary including record, win rate, net profit, and ROI. After viewing, the tracker list redisplays so you can pick another. Press `Q` to return to the main menu.
- **Pre-Tipoff Review:** `[P]` command compares fresh post-fetch data against your placed bets. For each bet it shows new injuries (OUT/GTD), line movement (current market vs your logged line), recalculated edge using the live fair line, and an action suggestion (🟢 HOLD / 🟡 REVIEW / 🔴 HEDGE). Run `./fetch_all_nba_data.sh odds,injuries` first, then `[P]` to see what changed.
- **Optimized Performance:** All analysis runs on local cached data — no network latency, no retries.
- **Kelly Criterion Integration:** Calculates conservative bankroll risk for every edge found.
- **CLV Tracking:** Fetches live odds from The Odds API to measure Closing Line Value — the gold standard for proving real edge.
- **Baseline Fallback:** If no cache exists, the engine uses hard-coded league-average baselines so it never crashes.

### **Project Structure & File Guide**

| File/Folder                      | Purpose                                                                                                                                                                                                                                                                        |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `nba_engine_ui.py`               | Main command-line interface. Reads schedule from cached JSON (ESPN-sourced). Supports `[G#]` analysis, `[P]` pre-tipoff review, `[U]` upcoming games, `[B]` bet tracker viewer, `[C]` custom matchups, `[R]` refresh all caches, and graceful Ctrl+C exit. Zero network calls. |
| `nba_analytics.py`               | Core analytics logic and spread prediction. Bayesian Star Tax, late-scratch detection, fatigue adjustments. Reads exclusively from pre-fetched cache files.                                                                                                                    |
| `nba_teams_static.py`            | Local static module with all 30 NBA teams — IDs, names, abbreviations, nicknames. Replaces `nba_api.stats.static` with zero network dependency.                                                                                                                                |
| `schedule_prefetch.py`           | Prefetches today + 7 days of NBA schedule from ESPN (primary) with NBA.com fallback. Writes `nba_schedule_cache.json`.                                                                                                                                                         |
| `star_tax_prefetch.py`           | Selenium scraper that fetches player NET_RATING from NBA.com's advanced stats page for all 30 teams. Writes `nba_star_tax_cache.json`.                                                                                                                                         |
| `nba_data_fetcher_advanced.py`   | Selenium-based NBA.com advanced team stats scraper. Writes `nba_stats_cache.json`.                                                                                                                                                                                             |
| `injury_scraper.py`              | Scrapes CBS Sports for NBA injury data and caches to `nba_injuries.csv`.                                                                                                                                                                                                       |
| `nba_lineup_and_news_monitor.py` | Scrapes ESPN for NBA lineups/injuries and fetches breaking news via ESPN RSS feed.                                                                                                                                                                                             |
| `rest_penalty_scraper.py`        | Scrapes and caches rest/fatigue penalty data per team to `nba_rest_penalty_cache.csv`.                                                                                                                                                                                         |
| `cache_nba_news.py`              | Fetches ESPN RSS news feed and caches to `nba_news_cache.json` for offline use.                                                                                                                                                                                                |
| `schedule_scraper.py`            | Multi-source NBA schedule comparison tool. Scrapes ESPN and NBA.com to compare and validate game data side-by-side.                                                                                                                                                            |
| `edge_analyzer.py`               | Edge decomposition and diagnostics — breaks down how each component (efficiency, HCA, fatigue, star tax) contributes to the predicted spread.                                                                                                                                  |
| `update_results.py`              | Auto-fetches final scores from ESPN JSON API and updates bet tracker CSVs with WIN/LOSS/PUSH results. Also populates CLV (Closing Line Value) from cached odds.                                                                                                                |
| `odds_api.py`                    | Fetches live NBA spreads from The Odds API and caches them for CLV tracking. Run via `fetch_all_nba_data.sh` or standalone.                                                                                                                                                    |
| `post_mortem.py`                 | Post-game analysis tool for reviewing bet outcomes and model accuracy.                                                                                                                                                                                                         |
| `fetch_all_nba_data.sh`          | Master pipeline script — runs all 8 prefetchers in order, validates 6 core caches, reports summary. Accepts an optional argument to fetch a single feed (e.g., `odds`, `injuries`) or comma-separated combo (e.g., `odds,injuries`). With no argument, refreshes everything.   |
| `.env.example`                   | Template for environment config. Contains `ODDS_API_KEY` for CLV tracking and `STALE_HOURS` for cache freshness threshold (default: 12).                                                                                                                                       |
| `nba_stats_cache.json`           | Cached NBA team advanced stats (auto-generated by `nba_data_fetcher_advanced.py`). Source: NBA.com.                                                                                                                                                                            |
| `nba_schedule_cache.json`        | Cached NBA schedule for today + 7 days (auto-generated by `schedule_prefetch.py`). Source: ESPN.                                                                                                                                                                               |
| `nba_star_tax_cache.json`        | Cached player NET_RATING data for all 30 teams (auto-generated by `star_tax_prefetch.py`). Source: NBA.com.                                                                                                                                                                    |
| `nba_injuries.csv`               | Cached injury report data (auto-generated by `injury_scraper.py`). Source: CBS Sports.                                                                                                                                                                                         |
| `nba_news_cache.json`            | Cached NBA news items from ESPN RSS (auto-generated by `cache_nba_news.py`). Source: ESPN.                                                                                                                                                                                     |
| `nba_rest_penalty_cache.csv`     | Cached rest/fatigue penalty data per team (auto-generated by `rest_penalty_scraper.py`). Source: ESPN.                                                                                                                                                                         |
| `odds_cache.json`                | Cached NBA spread odds from The Odds API (auto-generated by `odds_api.py`). Used for CLV calculation.                                                                                                                                                                          |
| `game_schedule.csv`              | Local schedule data for rest/fatigue calculations.                                                                                                                                                                                                                             |
| `bet_tracker_YYYY-MM-DD.csv`     | Daily log of all bets with timestamp, fair lines, edges, Kelly calculations, confidence grade, bet type, sportsbook, odds, and real-dollar tracking (including auto-calculated ToWin).                                                                                         |
| `text_to_image.py`               | Renders terminal text output as a full-length PNG screenshot with color-coded lines. Usage: `python text_to_image.py <input.txt> [output.png]`                                                                                                                                 |
| `requirements.txt`               | Python dependencies for the project. Note: `nba_api` has been fully removed.                                                                                                                                                                                                   |
| `BETTING_GUIDE.md`               | Guide to using the engine for betting, including manual steps and best practices.                                                                                                                                                                                              |
| `README.md`                      | This file.                                                                                                                                                                                                                                                                     |

---

## 🏗️ Data Pipeline Architecture

The engine separates **data fetching** (network-dependent) from **analysis** (cache-only). This design ensures the UI never stalls on a slow or unreachable API.

```
┌─────────────────────────────────────────────────────────────┐
│                  fetch_all_nba_data.sh                       │
│  Runs 8 prefetchers → validates 6 core caches → logs all    │
│                                                             │
│  Usage:                                                     │
│    ./fetch_all_nba_data.sh              (all feeds)          │
│    ./fetch_all_nba_data.sh odds         (just odds/CLV)      │
│    ./fetch_all_nba_data.sh injuries     (just injuries)      │
│    ./fetch_all_nba_data.sh odds,injuries (combo)             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  nba_data_fetcher_advanced.py  ──→  nba_stats_cache.json    │  (NBA.com Selenium)
│  injury_scraper.py             ──→  nba_injuries.csv        │  (CBS Sports)
│  nba_lineup_and_news_monitor.py                              │  (ESPN)
│  rest_penalty_scraper.py       ──→  nba_rest_penalty_cache  │  (ESPN Selenium)
│  cache_nba_news.py             ──→  nba_news_cache.json     │  (ESPN RSS)
│  schedule_prefetch.py          ──→  nba_schedule_cache.json │  (ESPN API)
│  star_tax_prefetch.py          ──→  nba_star_tax_cache.json │  (NBA.com Selenium)
│  odds_api.py                   ──→  odds_cache.json         │  (The Odds API)
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                    nba_engine_ui.py                          │
│        Reads ONLY from cache files — zero network calls      │
│        Startup: < 1 second                                   │
└─────────────────────────────────────────────────────────────┘
```

### Data Sources

| Cache        | Source       | Feed                                         | Refresh Method                 |
| ------------ | ------------ | -------------------------------------------- | ------------------------------ |
| Team Stats   | NBA.com      | Selenium scrape of `/stats/teams/advanced`   | `nba_data_fetcher_advanced.py` |
| Injuries     | CBS Sports   | HTML scrape of `/nba/injuries/`              | `injury_scraper.py`            |
| News         | ESPN         | RSS feed `espn.com/espn/rss/nba/news`        | `cache_nba_news.py`            |
| Rest Penalty | ESPN         | Selenium scrape of scoreboard                | `rest_penalty_scraper.py`      |
| Schedule     | ESPN         | JSON API `site.api.espn.com`                 | `schedule_prefetch.py`         |
| Star Tax     | NBA.com      | Selenium scrape of `/stats/players/advanced` | `star_tax_prefetch.py`         |
| Odds/CLV     | The Odds API | REST API (500 req/month free)                | `odds_api.py`                  |

---

## 🚦 Recommended User Workflow

Follow these steps to get the most out of the NBA Prediction Engine:

1. **Update and Fetch Data**
   - Before analyzing games, refresh all caches by either:
     - Running `bash fetch_all_nba_data.sh` from the terminal (all feeds), or
     - Using the `[R] Refresh Data` command inside the engine UI.
   - This fetches advanced stats (NBA.com), injuries (CBS Sports), rest penalties (ESPN), news (ESPN RSS), schedule (ESPN), star tax (NBA.com), and odds (The Odds API).
   - The script validates all 6 core cache files and reports a summary.
   - **Selective fetch:** Pass a feed name to refresh only specific data:
     - `./fetch_all_nba_data.sh odds` — just odds (pre-tipoff CLV snapshot)
     - `./fetch_all_nba_data.sh injuries` — just injuries (late scratch check)
     - `./fetch_all_nba_data.sh odds,injuries` — comma-separated combo
     - Also: `stats`, `news`, `schedule`, `rest`, `startax`

2. **Analyze Games and Generate Recommendations**
   - Run the engine: `python nba_engine_ui.py`
   - The UI displays today's NBA schedule from the pre-cached ESPN schedule (sub-second load).
   - The **DATA CACHE FRESHNESS** banner shows the timestamp and source of every cache, with warnings if any data is stale (configurable via `STALE_HOURS` in `.env`).
   - The **game dashboard** shows two key status indicators for each game:
     - **🎫 Bet placed** — a ticket emoji appears next to any game you've already bet on, with a summary count (e.g., "4/9 games")
     - **📈 Per-window CLV freshness** — games are grouped by tip-off time (e.g., 7:00 PM, 7:30 PM, 10:00 PM). Each window shows whether odds are ✅ Fresh (fetched within 30 min of tip), ⚠️ Stale, or ❌ Not fetched. The dashboard also prints the exact command and time to run it (e.g., `→ Run at ~6:45 PM: ./fetch_all_nba_data.sh odds,injuries`).
   - Use `[U]` to browse the next 7 days of upcoming games and select any for preview analysis.
   - **Note:** Upcoming games (`U#`) run in **preview mode** — full analysis is shown but not logged to the bet tracker. This ensures bets are only recorded with fresh game-day data. Re-analyze on game day to log.
   - For each game, input the market line when prompted.
   - The engine calculates the fair line, edge, and confidence, factoring in:
     - Advanced stats (offensive/defensive ratings, pace) — from NBA.com cache
     - Injury data — from CBS Sports cache
     - Late-breaking news — from ESPN RSS cache
     - Rest/fatigue penalties and dynamic home-court advantage
     - Star Tax (player NET_RATING impact) — from NBA.com cache

3. **Automated Flagging & Recommendation**
   - Every game shows a **bet recommendation** with a signal tier:
     - 🚨 **REVIEW REQUIRED** (edge > cap) — edge capped, model may be missing key info. Investigate before betting.
     - 🔥 **STRONG SIGNAL** (edge ≥ 5, HIGH confidence) — highest conviction
     - 📊 **LEAN** (edge ≥ 3) — moderate edge, worth considering
     - 📉 **LOW EDGE** (<3 pts) — thin margin, proceed with caution
   - The **edge cap** (default: 10 pts) is tunable via the Bankroll Tracker (`post_mortem.py` → [5] → [R]). Edges above the cap are clamped and flagged as suspicious.
   - If late-breaking lineup/injury news is detected, the UI will alert you to double-check before betting.

4. **Logging and Tracking**
   - Today's games (`G#`) and custom matchups (`C`) are logged to a date-stamped CSV (`bet_tracker_YYYY-MM-DD.csv`) for post-mortem review.
   - **Upcoming games (`U#`) are not logged** — they run in preview mode since injury/line data may change by game day.
   - Use `[B]` to **view bet tracker history** at any time — select a single day's tracker or view all combined. The viewer shows a formatted table of every bet with matchup, pick, edge, odds, stake, result, and payout, plus a P&L summary (record, win rate, net profit, ROI).
   - You'll be prompted for:
     - **Pick** — defaults to the engine's recommendation, but you can override with any team name
     - **Bet Type** — Spread (default), Moneyline, or Over/Under
     - **Sportsbook**, **Odds**, and **Bet amount** (all optional — press Enter to skip)
   - The engine automatically records the **Timestamp**, **Confidence** grade, and **ToWin** (calculated from your odds and stake).
   - When results are populated, `update_results.py` auto-calculates the **Payout** column using American odds math.

5. **Post-Analysis**
   - Run `python update_results.py` to auto-populate WIN/LOSS results from ESPN.
   - Run `python post_mortem.py` for the full performance analyzer:
     - **[1] Single-Day Post-Mortem** — detailed win/loss breakdown with injury and margin analysis
     - **[2] Lifetime Performance Dashboard** — all-time record, ROI, streaks, drawdown, and pro-level verdict
     - **[3] Edge Calibration Report** — do bigger edges win at higher rates?
     - **[4] Daily Trend & Profit Curve** — cumulative P/L over time with ASCII chart
     - **[5] Bankroll Tracker** — real-dollar bankroll tracking with Kelly bet sizing

This workflow ensures your predictions are based on the most current cached data, with built-in alerts for late-breaking news and injuries, and a clear audit trail for every bet.

### ⏱️ Recommended Pre-Tipoff Refresh Schedule

| Time                        | Command                                 | Purpose                                |
| --------------------------- | --------------------------------------- | -------------------------------------- |
| Morning                     | `./fetch_all_nba_data.sh`               | Full refresh of all 7 feeds            |
| 10–15 min before early tips | `./fetch_all_nba_data.sh odds,injuries` | Closing line snapshot + late scratches |
| After early tip fetch       | `[P]` in engine UI                      | Pre-tipoff review of placed bets       |
| 10–15 min before late tips  | `./fetch_all_nba_data.sh odds`          | 2nd CLV snapshot for late-window games |
| After games finish          | `python update_results.py`              | Scores + CLV + P&L                     |

For a single-window slate (all games tip within ~1 hour), one pre-tip `odds,injuries` run is sufficient. For split slates (e.g., 7 PM + 10 PM ET), run `odds` a second time before the late window to capture tighter closing lines.

**You don't need to memorize this schedule.** The engine dashboard automatically groups games by tip-off window and displays the exact time and command for each fetch, with live CLV freshness status. Just follow the `→ Run at ~TIME` prompts that appear below the game list.

> **📡 Cache-Only Schedule:** The engine loads the schedule from a pre-cached ESPN JSON file (`nba_schedule_cache.json`) — no live API calls at startup. Run `bash fetch_all_nba_data.sh` or `[R]` to refresh. The source is displayed in the banner (e.g., `(ESPN)`).
>
> **⏱️ Cache Freshness Warnings:** The banner displays the age and source feed of every cache. If any cache is older than the configurable threshold (default: 12 hours, set via `STALE_HOURS` in `.env`), the UI warns you to refresh before analyzing games.
>
> **🎫 Bet Status & CLV Dashboard:** The game schedule shows a 🎫 ticket emoji next to every game with a logged bet, plus a count summary (e.g., "4/9 games"). Below the schedule, games are grouped by tip-off window with per-window CLV odds freshness. Each window shows whether your cached odds are fresh (within 30 min of tip-off), stale, or missing — along with the exact time and command to run. This eliminates guesswork: just follow the `→ Run at ~TIME` prompts to capture closing lines for each window.
>
> **📆 Upcoming Games:** Use the `[U]` command to browse the next 7 days of NBA games. Each game gets a selectable ID (e.g., `U1`, `U12`) so you can run pre-game analysis days in advance — great for scouting before lines move. Upcoming games run in **preview mode**: full analysis is displayed but not logged to the bet tracker, since injuries, lines, and rest data may change by game day. Re-analyze on game day with `[G#]` to log a real bet.
>
> **💡 Custom Matchups:** Use `[C]` to analyze any matchup manually, even hypothetical ones. Just enter the away and home team names and the engine runs the full analysis using cached stats, injuries, and rest data.
>
> **📒 Bet Tracker Viewer:** Use the `[B]` command to review your betting history without leaving the engine. It lists all `bet_tracker_*.csv` files with bet counts, lets you select one (or `A` for all combined), and displays a formatted table with matchup, pick, edge, odds, bet amount, result, payout, and notes. A P&L summary shows your record, win rate, total wagered, net profit/loss, and ROI. The combined view prefixes each bet ID with the tracker date for easy cross-referencing.>
> **🔍 Pre-Tipoff Review:** Use the `[P]` command after running `./fetch_all_nba_data.sh odds,injuries` to audit your placed bets against fresh data. For each bet, the review shows: (1) injury changes — new OUT or GTD players since you placed the bet, (2) line movement — how the market spread has shifted, (3) updated edge — recalculated fair line vs current market, and (4) action suggestion — 🟢 HOLD (edge stable/improved), 🟡 REVIEW (edge thin or situation changed), or 🔴 HEDGE (edge collapsed + key player OUT). A summary at the bottom tallies HOLD/REVIEW/HEDGE counts across all bets.

---

## 📊 Post-Bet Analysis: Entering Wins & Losses

After games finish, update your bet tracker CSV and run the post-mortem tool to review model accuracy.

### Step 1: Update Results (Automatic)

Run the result updater to automatically fetch final scores and populate WIN/LOSS:

```bash
python update_results.py
```

The script will:

1. List all available `bet_tracker_*.csv` files with their pending/complete status
2. Let you select a specific file or update all pending files at once
3. Fetch final scores from the ESPN JSON API (`site.api.espn.com`)
4. Determine WIN/LOSS based on whether your pick covered the spread
5. Save the updated CSV with results and final scores

**Example output:**

```
  Available bet tracker files:

    [1] bet_tracker_2026-02-10.csv  (4 games, 4 pending)
    [2] bet_tracker_2026-02-09.csv  (11 games, all complete)
    [A] Update ALL files with pending games
    [Q] Quit

  Select: 1
  ✅ G1: Pacers @ Knicks → WIN  (Final Score: Pacers 115 - Knicks 108)
  ❌ G2: Clippers @ Rockets → LOSS  (Final Score: Clippers 99 - Rockets 112)
  🟰 G3: Lakers @ Suns → PUSH  (Final Score: Lakers 110 - Suns 120)
```

### Step 1b: Manual Update (Alternative)

You can also edit the CSV directly. Open the bet tracker CSV and change each row's `Result` from `PENDING` to `WIN` or `LOSS`. Add the final score in the `Notes` column for margin analysis.

| Column        | Value                                | Description                                                   |
| ------------- | ------------------------------------ | ------------------------------------------------------------- |
| `Timestamp`   | `2026-02-12 13:17:16`                | Auto-recorded when the bet is logged                          |
| `Confidence`  | `HIGH`, `MEDIUM`, `LOW`              | Model confidence grade (auto-saved from engine)               |
| `Pick`        | `Bucks`, `Thunder`, etc.             | Defaults to recommendation; can be overridden                 |
| `Type`        | `Spread`, `Moneyline`, `Over/Under`  | Bet type (defaults to Spread)                                 |
| `Book`        | `DraftKings`, `FanDuel`, etc.        | Sportsbook (optional, entered at bet time)                    |
| `Odds`        | `-110`, `+150`, etc.                 | American odds (optional, entered at bet time)                 |
| `Bet`         | `50`, `100`, etc.                    | Dollar amount wagered (optional)                              |
| `ToWin`       | `89.29`, `150.00`, etc.              | Auto-calculated from Odds and Bet amount                      |
| `Result`      | `WIN`, `LOSS`, `PUSH`, or `PENDING`  | Auto-populated by `update_results.py` or set manually         |
| `Payout`      | `95.45`, `-50`, `0.00`, etc.         | Auto-calculated from Bet/Odds on WIN/LOSS/PUSH                |
| `ClosingLine` | `-5.5`, `+3.0`, etc.                 | Consensus closing spread from The Odds API (auto-populated)   |
| `CLV`         | `+1.5`, `-0.5`, etc.                 | Closing Line Value — how much better your line was vs closing |
| `Notes`       | `Final Score: Team1 123 - Team2 110` | Auto-populated or set manually for margin analysis            |

### Step 2: Run the Post-Mortem Analyzer

```bash
python post_mortem.py
```

You'll see a menu with five options:

```
  [1] Single-Day Post-Mortem
  [2] Lifetime Performance Dashboard
  [3] Edge Calibration Report
  [4] Daily Trend & Profit Curve
  [5] Bankroll Tracker
  [Q] Quit
```

### Menu Options

**[1] Single-Day Post-Mortem** — Enter a date to review that day's bets:

- Win/Loss/Pending counts for all bets and high-signal bets (Edge ≥ 5)
- Loss details with margin of defeat, injury impact, and low-edge flags
- Win details with average margin of victory
- Day P/L in units and real dollars (when bet amounts are tracked)

**[2] Lifetime Performance Dashboard** — All-time aggregate stats:

- Overall record, win rate, and letter grade (Elite / Pro-Level / Profitable / Below Breakeven)
- Total P/L in units and Kelly-weighted units
- **💰 Real Money P/L** — net profit/loss in dollars, total wagered, and ROI (or setup tip if no bet amounts tracked)
- **Sportsbook breakdown** — win rate and P/L per book (or tip to enter book names when logging)
- **Confidence breakdown** — win rate by HIGH/MEDIUM/LOW grade (or note if data unavailable)
- High-signal bet performance
- **📈 CLV Summary** — average Closing Line Value, positive CLV rate, CLV by wins/losses (or setup guide if no odds cached)

> **What is CLV?** Closing Line Value measures whether you got a better number than the final market line at tip-off. Sportsbooks don't provide this — you calculate it yourself:
>
> 1. Record the line when you place your bet (your **Market Line**)
> 2. The engine caches the consensus closing line from 15+ sportsbooks right before tip-off
> 3. **CLV = Closing Line − Your Market Line** (positive = you beat the market)
>
> Why it matters: research shows that bettors who consistently beat the closing line are profitable long-term, regardless of short-term variance. CLV is the single best predictor of real edge vs. just running hot.

- Edge calibration (do bigger edges win more often?)
- Streaks, max drawdown, and current balance
- Daily trend table (with dollar P/L column when available)
- **Pro-Level Verdict** — 6-point checklist:
  - ATS Win Rate > 52.4% (break-even at -110)
  - Positive ROI
  - High-Signal Win Rate > 55%
  - Edge Calibration (higher edges = higher win rate)
  - Sufficient Sample Size (20+ bets)
  - Positive CLV (beating closing lines, when data available)

**[3] Edge Calibration Report** — Fine-grained breakdown by edge bucket (0–3, 3–5, 5–8, 8–10, 10–15, 15–20, 20+) with visual bars, P/L, and Edge-vs-Win-Rate correlation.

**[4] Daily Trend & Profit Curve** — Day-by-day P/L with cumulative rolling win rate and an ASCII profit curve chart.

**[5] Bankroll Tracker** — Set a starting bankroll, unit size, and edge cap, then track day-by-day balance changes with real dollars. Includes Quarter-Kelly recommended bet sizing based on lifetime win rate. Press `[R]` to reset your settings (bankroll, unit size, edge cap) when you're ready to scale up.

---

## 🧰 Optional Utility Tools

These scripts provide additional analysis, data checks, and manual overrides for advanced users:

- **injury_scraper.py**
  - Manually scrape and save the latest NBA injury data from CBS Sports for custom analysis or troubleshooting.
  - Usage: `python injury_scraper.py`

- **nba_lineup_and_news_monitor.py**
  - Scrape ESPN for lineups/injuries and fetch NBA news headlines via RSS. Useful for monitoring late scratches and breaking news.
  - Usage: `python nba_lineup_and_news_monitor.py`

- **text_to_image.py**
  - Render terminal output as a full-length PNG screenshot with a dark background and color-coded lines (green for wins, red for losses, yellow for verdicts). Useful for sharing dashboards and session results.
  - Usage: `python text_to_image.py <input.txt> [output.png]`
  - Tip: Use the VS Code **Terminal Capture** extension to save terminal output to a text file first.

- **schedule_scraper.py**
  - Multi-source NBA schedule comparison tool. Fetches today's (or any date's) games from ESPN and NBA.com, then prints a side-by-side comparison grid showing which sources agree. Useful for validating schedule data or debugging missing games.
  - Usage:
    ```bash
    python schedule_scraper.py              # Compare sources for today
    python schedule_scraper.py 2026-02-22   # Compare sources for a specific date
    ```

These tools are optional but recommended for power users who want deeper insight, custom data, or extra validation before betting.

---

## 🛠️ VS Code Installation & Setup (macOS)

### **Step 1: Open Your Project**

1. Launch **Visual Studio Code**.
2. Go to `File > Open Folder...` and select the folder containing your `.py` files.

### **Step 2: Set Up a Virtual Environment (Recommended)**

This keeps your project libraries isolated and prevents "Module Not Found" errors.

1. Open the integrated terminal in VS Code (`Terminal > New Terminal`).
2. Type the following commands:

```bash
python3 -m venv .venv
source .venv/bin/activate

```

3. You should now see `(.venv)` at the start of your terminal prompt.

### **Step 3: Install Dependencies**

Run this command in your VS Code terminal to install dependencies:

```bash
pip install -r requirements.txt

```

### **Step 4: Fetch NBA Data & Set Up API Keys**

Run the data pipeline to populate all caches (stats, injuries, news, schedule, star tax, odds):

```bash
bash fetch_all_nba_data.sh
```

This runs 8 prefetchers, validates 6 core cache files, and reports a summary. The engine will not function correctly without cached data — run this first.

After the initial full fetch, you can selectively refresh individual feeds:

```bash
./fetch_all_nba_data.sh odds          # Pre-tipoff CLV snapshot
./fetch_all_nba_data.sh injuries      # Late scratch check
./fetch_all_nba_data.sh odds,injuries # Combo
```

**Optional — Enable CLV Tracking:**

1. Sign up for a free API key at [the-odds-api.com](https://the-odds-api.com).
2. Copy the template and add your key:

```bash
cp .env.example .env
# Edit .env and replace "your_api_key_here" with your real key
```

**Optional — Configure Stale Cache Threshold:**

Edit `.env` to change when the UI warns about old data (default: 12 hours):

```bash
STALE_HOURS=12
```

The engine works without these — CLV columns will simply be left blank, and the stale threshold defaults to 12 hours.

### **Step 5: Select the Python Interpreter**

1. Press `Cmd + Shift + P` and type **"Python: Select Interpreter"**.
2. Choose the one that starts with `./.venv/bin/python`. This ensures VS Code uses the libraries you just installed.

### **Step 6: Run the Engine**

1. Open `nba_engine_ui.py` in the editor.
2. Click the **"Play"** button in the top-right corner, or type this in the terminal:

```bash
python nba_engine_ui.py

```

### **VS Code YouTube Tutorials**

- [How to Set Up Python Development in VS Code on Mac](https://www.youtube.com/watch?v=4CJHjqZfH7A) - This video provides a clear walkthrough for setting up a virtual environment and running Python scripts on macOS, which is essential for getting your NBA engine running smoothly.
- [How to Run Python in Visual Studio Code on Windows 10/11](http://www.youtube.com/watch?v=mIVB-SNycKI) - Step-by-step guide you on how to run Python in Visual Studio Code on Windows 10/11 + Python for Python Developers on Windows 10/11 OS.

---

## 🏁 Pro Troubleshooting

- **Stale Data Warnings:** The engine displays cache freshness in the banner. If you see ⚠️ warnings, run `[R]` or `bash fetch_all_nba_data.sh` to refresh.
- **Missing Cache Files:** If a cache file is missing, the banner shows 🚨 MISSING CACHE. Run the data pipeline to populate it.
- **Slow First Run:** The first `bash fetch_all_nba_data.sh` run takes longer (Selenium scraping). Subsequent UI runs are < 1 second since they only read cached files.
- **Connection Error:** If ESPN or NBA.com blocks your IP, toggle your iPhone's **Airplane Mode** for 5 seconds to reset your hotspot's IP address.
- **Missing Data:** If the CSV isn't updating, ensure you have "Write" permissions for the folder you opened in VS Code.
- **ChromeDriver Errors:** The advanced stats scraper (`nba_data_fetcher_advanced.py`) and star tax scraper (`star_tax_prefetch.py`) use Selenium and require Google Chrome. Install Chrome from [google.com/chrome](https://www.google.com/chrome/). ChromeDriver is bundled with Chrome and managed automatically.
- **No CLV Data:** If CLV columns are blank, ensure your `.env` file contains a valid `ODDS_API_KEY` and run `./fetch_all_nba_data.sh odds` 10–15 minutes before game tip-off to cache the closing lines. For split slates, run it again before the late window.
- **Stale Threshold Too Sensitive:** Adjust `STALE_HOURS` in `.env` (default: 12). Set higher for less frequent refreshing.

---

## 🧠 The "Nitty-Gritty": How the Engine is Modeled

The model operates on the principle that NBA games are won by possession efficiency. It translates advanced ratings into a point spread using the following multi-layer logic:

### 1. The Core Efficiency Formula

We calculate the expected point differential per 100 possessions by cross-referencing offensive and defensive ratings over a **rolling 10-game window**:

$$Raw\ Diff = (OffRtg_{home} - DefRtg_{away}) - (OffRtg_{away} - DefRtg_{home})$$

This value is then normalized to the projected pace of the game:

$$Points_{spread} = Raw\ Diff \times \left( \frac{Pace_{avg}}{100} \right)$$

### 2. Situational Adjustments (The "Edge")

To move beyond a 50% accuracy rate, the engine applies three situational layers:

- **Fatigue Adjuster (B2B):** Detects if a team played the previous night. A **-2.5 point penalty** is applied to tired teams to account for drops in rebounding and defensive intensity.
- **Dynamic Home Court (HCA):** Instead of a flat +3.0, the engine calculates a team-specific HCA based on their season-long Home vs. Road Net Rating.
- **Star Tax (Injury Impact):** Scrapes injury reports from CBS Sports. If a star is out, the engine looks up their individual **NET_RATING** from the pre-cached NBA.com player advanced stats and subtracts that value from the team's total power rating.

### 3. The Sanity Check (Volatility Filter)

If the **Calculated Edge** (Difference between Engine Line and Market Line) exceeds **11.0 points**, the engine flags the game as high-volatility. This usually indicates a market-moving event (like a trade or late scratch) that the math has detected but requires human verification.

---

### 📉 Mathematical Modeling Section

The engine uses a series of possession-based linear equations to derive the fair value of a matchup.

#### 1. Efficiency Differential ()

We first calculate the net efficiency margin by comparing how each team's offense performs against the opponent's defense:

$$Raw\ Diff = (OffRtg_{home} - DefRtg_{away}) - (OffRtg_{away} - DefRtg_{home})$$

#### 2. Pace Normalization

Since is calculated per 100 possessions, we must scale it to the game's projected (the total number of possessions for both teams):

$$Points_{spread} = Raw\ Diff \times \left( \frac{Pace_{avg}}{100} \right)$$

#### 3. Situational Final Line ()

The final projected spread incorporates the Dynamic Home Court Advantage (), the Fatigue Adjustment (), and the Star Tax ():

$$Fair\ Line = Points_{spread} + HCA + \sum Rest + \sum Injury$$

---

## 🛠️ Edge Cap & Review Required

When the engine's predicted edge exceeds your **edge cap** (default: 10 pts, tunable via `post_mortem.py` → [5] → [R]), the edge is clamped and the game is flagged as **🚨 REVIEW REQUIRED**. This guardrail exists because historically, extreme edges (15+ pts) have performed at ~40% — worse than moderate edges — suggesting the model is probably reacting to noise rather than a true market inefficiency.

For example, here's how the engine flagged suspicious edges on the **February 8, 2026** slate, where massive injury-report noise drove inflated predictions:

### 🔍 Example Breakdown

| Game              | Edge          | Why the Alert Triggered                                                                                                                                                                                                                                                             |
| ----------------- | ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **G1: NYK @ BOS** | **12.59 pts** | **The Tatum Factor:** Jayson Tatum is officially **OUT** (Achilles). Your engine's "Star Tax" likely hammered the Celtics' rating, while the market is still giving them a -3.5 favorite status based on their depth.                                                               |
| **G3: IND @ TOR** | **16.24 pts** | **The Zubac/Haliburton Void:** This is a "chaos" game. The Pacers are missing Tyrese Haliburton and Ivica Zubac, while Toronto has several "Questionables." The 16-point gap suggests the market thinks Toronto is healthy, while your engine sees two depleted rosters.            |
| **G4: LAC @ MIN** | **10.6 pts**  | **Clippers Trade/Injury Flux:** The Clippers are listed with several "Out" players (Garland, Mathurin, Jackson) due to pending trades and injuries. Your engine likes the Clippers +9.5 because it sees Minnesota's Poeltl being out as a bigger net-negative than the market does. |

---

### 🛠️ How to Handle these Alerts

When you see an edge above your cap (default: 10 pts), the engine caps the displayed edge and shows a **🚨 REVIEW REQUIRED** warning. The cap is tunable — adjust it in the Bankroll Tracker (`post_mortem.py` → [5] → [R] Reset Settings → Edge Cap). Use the "Human in the Loop" method:

1. **Check the "Questionables":** For G1, the Knicks have **Karl-Anthony Towns, Josh Hart, and OG Anunoby** all listed as Questionable. If all three play, your "Recommended Side" (Knicks) is a lock. If all three sit, that 12.59-point edge might actually vanish or flip.
2. **Verify the Scraper:** Since the scraper pulls from CBS, sometimes it misses a "Game Time Decision" (GTD) that was just announced on Twitter/X.
3. **The "Trap Line" Rule:** If your engine says the Knicks should be favored by 9, but Vegas has them as +3.5, ask yourself: _"What does Vegas know that my 10-game rolling average doesn't?"_ (Usually, it's a specific player matchup or a "revenge game" narrative).

### 🔒 Edge Cap Audit (Lifetime Dashboard)

The Lifetime Dashboard (`post_mortem.py` → [2]) now includes an **Edge Cap Audit** section that helps you decide whether the cap needs adjusting:

- **Capped vs. Uncapped Win Rates** — side-by-side comparison to see if capped bets underperform
- **Raw Edge Distribution** — min/max/avg/median of the uncapped edges for capped bets
- **Individual Capped Bet Log** — every capped bet with its raw edge, capped edge, and result
- **Recommendation** — once 5+ decided capped bets exist, the system recommends keeping, raising, or lowering the cap

The CSV now stores both `Raw_Edge` (uncapped) and `Edge_Capped` (YES/NO) columns. Historical bets without these columns are automatically reconstructed from `abs(Fair - Market)`.

---

## 🗺️ Roadmap

Planned improvements to sharpen the model's accuracy and close gaps with market pricing.

### 1. Enhanced Star Tax — Usage-Weighted Injury Impact

**Status:** Planned

The current Star Tax uses on/off court plus-minus to estimate the impact of missing players. This undersells the effect of losing high-usage stars whose offensive burden can't easily be redistributed.

**Upgrade:** Weight the Star Tax by each player's **usage rate** and **minutes share**, not just on/off +/-. A 30% usage player being out has an outsized effect on the offense compared to a 15% usage player, even if their raw +/- is similar. This better reflects how the remaining roster absorbs the lost production.

**Expected impact:** More accurate injury adjustments for star-dependent teams (e.g., Luka/Mavs, Jokic/Nuggets), reducing false edges caused by the model undervaluing star absences.

### 2. Archetype Mismatch Flag — Targeted Defensive Adjustment

**Status:** Planned

Team-level defensive ratings capture overall defensive quality but miss **positional mismatches** caused by injuries. When a team loses its primary perimeter defender and faces a top-tier wing offense, the team DEF_RATING doesn't reflect the specific vulnerability.

**Upgrade:** Add a simple "archetype mismatch" flag that applies a **1–2 point adjustment** when:

- A team is missing its primary wing/perimeter defender (identified via defensive minutes and matchup data)
- The opposing team has a top-5 wing-heavy offense (high usage from wing players)

This is the one area where individual defensive performance actually matters and isn't already captured in team-level ratings.

**Expected impact:** Catches 2–4 additional edges per week that the current model misses, particularly in playoff-intensity matchups where defensive assignments are more targeted.

### 3. Travel Distance Adjustment

**Status:** TODO  
**Feasibility:** Easy — schedule data + city coordinates  
**Expected impact:** Medium

Long-haul travel measurably affects performance. Portland → Miami is brutal; LAL → LAC is nothing. Add a travel distance factor using arena coordinates and the schedule to apply a small penalty (0.5–1.5 pts) for cross-country flights, especially when combined with B2B or short rest.

Also accounts for **altitude** — Denver at 5,280 ft is a real factor; visiting teams shoot ~2% worse from 3 at altitude.

### 4. 3-Point Shooting Variance Regression

**Status:** TODO  
**Feasibility:** Easy — data already available in team stats  
**Expected impact:** Low-Medium

If a team shot 42% from 3 over the last 5 games vs. their season average of 36%, pros expect regression. The current 10-game rolling window partially captures this, but doesn't explicitly model 3P% mean reversion. Add a regression-to-mean adjustment on recent 3P% to avoid overweighting hot/cold shooting streaks.

### 5. Referee Assignment Tendencies

**Status:** TODO  
**Feasibility:** Medium — data exists on NBA.com  
**Expected impact:** Medium

Individual refs have measurable tendencies: foul rates, home FT disparity, pace of play. Some refs call 15% more fouls than others — that directly affects totals and spreads. Sharp bettors track ref assignments (released ~9am ET game day). Add a ref-tendency adjustment when crew data is available.

### 6. Schedule Context — Sandwich Games & Time Zone Travel

**Status:** TODO  
**Feasibility:** Easy-Medium — schedule data analysis  
**Expected impact:** Medium

Beyond B2B detection, add:

- **Rest disparity asymmetry** — 3 days rest vs. 1 day rest matters more than 2 vs. 1
- **"Sandwich games"** — a team plays a weak opponent between two marquee games and historically underperforms
- **West coast teams playing early East coast games** (noon tips after flying east)
- **Time zone penalty** — teams crossing 2+ time zones on short rest

### 7. Lineup-Specific Net Ratings

**Status:** TODO  
**Feasibility:** Medium — available via NBA.com lineup stats pages  
**Expected impact:** Medium

Go beyond "who's out" to model "who replaces them." Five-man lineup net ratings show how specific combos perform together. When a starter is out, _who_ gets those minutes matters more than the absence itself. Factor in minutes distribution shifts and rotation depth (a team missing its 6th man in a B2B is worse than missing them with 3 days rest).

### 8. Closing Line Value (CLV) Tracking

**Status:** ✅ Implemented  
**Feasibility:** Medium (using The Odds API free tier — 500 req/month)  
**Expected impact:** High

Tracks whether the engine's fair line beats the closing line, not just whether the bet wins. CLV is the gold standard metric for professional bettors — a positive CLV over time proves the model has real edge, even during losing streaks.

**Implementation:**

- `odds_api.py` fetches live spreads from The Odds API and caches consensus lines from 15+ sportsbooks
- `fetch_all_nba_data.sh` automatically refreshes odds alongside other data (or use `./fetch_all_nba_data.sh odds` for a targeted pre-tipoff refresh)
- `update_results.py` populates `ClosingLine` and `CLV` columns in bet tracker CSVs
- `post_mortem.py` lifetime dashboard shows CLV summary (avg CLV, positive CLV rate, CLV by result)
- CLV is included as a check in the Pro-Level Verdict (positive CLV = real edge)

### 9. Motivation & Game Theory Factors

**Status:** TODO  
**Feasibility:** Medium — requires season context logic  
**Expected impact:** Low-Medium

Account for non-statistical factors that move lines:

- **Tanking incentives** — teams in the lottery race actively lose late-season games
- **Playoff seeding strategy** — resting starters in meaningless late-season games
- **Revenge games** — traded players facing former teams within ~30 days perform above baseline (small but non-zero effect)
- **Division/rivalry intensity** — certain matchups consistently go under the total

### 10. Betting Market Structure Signals

**Status:** TODO  
**Feasibility:** Hard — requires real-time odds/market data  
**Expected impact:** High

Professional bettors don't just model the game — they model the _market_:

- **Steam moves** — sudden line movement from sharp books (Circa, Pinnacle) signals informed money
- **Reverse line movement** — line moves opposite to public betting percentages = sharp action
- **Stale lines** — smaller books are slow to adjust; pros arbitrage the gap

This is a data access problem more than a modeling problem — requires a live odds feed subscription.

---

### Feasibility Summary

| #   | Factor                                 | Feasibility | Impact     |
| --- | -------------------------------------- | ----------- | ---------- |
| 1   | Enhanced Star Tax (usage-weighted)     | Easy        | Medium     |
| 2   | Archetype Mismatch Flag                | Medium      | Medium     |
| 3   | Travel Distance Adjustment             | Easy        | Medium     |
| 4   | 3P% Variance Regression                | Easy        | Low-Medium |
| 5   | Referee Tendencies                     | Medium      | Medium     |
| 6   | Schedule Context (sandwich, time zone) | Easy-Medium | Medium     |
| 7   | Lineup-Specific Net Ratings            | Medium      | Medium     |
| 8   | CLV Tracking                           | ✅ Done     | High       |
| 9   | Motivation & Game Theory               | Medium      | Low-Medium |
| 10  | Market Structure Signals               | Hard        | High       |

### Design Principle

> **Don't bolt on raw individual stats.** Team-level ratings + Star Tax already encode most individual signal. Adding full box-score stats (PPG, RPG, APG) would double-count what's in the team numbers. Player-vs-player matchup data has tiny sample sizes and adds noise. The right approach is to **refine the existing adjustments** (Star Tax, injury impact) rather than adding a new layer of individual performance data.
>
> **Vegas's real edge isn't one secret factor — it's speed and data access.** They get injury confirmations 30 minutes before the public, they have proprietary player tracking data (Second Spectrum), and they process referee assignments instantly. The biggest alpha for a retail bettor isn't a better model — it's **timing** (betting before line movement) and **discipline** (only betting when your edge exceeds the vig).
