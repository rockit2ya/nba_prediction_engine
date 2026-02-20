# How to Use Your Enhanced NBA Betting Engine

## Quick Start — Place Bets Tonight

### 1. Fetch Fresh Data

```bash
./fetch_all_nba_data.sh              # Fetch ALL feeds (morning routine)
./fetch_all_nba_data.sh odds         # Just odds (pre-tipoff CLV snapshot)
./fetch_all_nba_data.sh injuries     # Just injuries (late scratch check)
./fetch_all_nba_data.sh news         # Just news + lineup monitor
./fetch_all_nba_data.sh stats        # Just team advanced stats
./fetch_all_nba_data.sh schedule     # Just schedule prefetch
./fetch_all_nba_data.sh rest         # Just rest penalty data
./fetch_all_nba_data.sh startax      # Just star tax (On/Off plus-minus)
./fetch_all_nba_data.sh odds,injuries # Comma-separated combo
```

With no argument, this runs all scrapers (team stats, injuries, rest penalties, news, schedule, star tax, and live odds) and caches the results locally. Pass a feed name (or comma-separated list) to refresh only specific data — ideal for quick pre-tipoff updates without re-running the full pipeline.

### 2. Run the Prediction Engine

```bash
python nba_engine_ui.py
```

The interactive UI will:

1. ✅ Display today's NBA games with **bet status** (🎫 = bet placed) and **per-window CLV freshness**
2. ✅ Show actionable fetch reminders for each tip-off window (e.g., "Run at ~6:45 PM: ./fetch_all_nba_data.sh odds,injuries")
3. ✅ Let you select a matchup to analyze
4. ✅ Calculate fair lines from team efficiency, injuries, rest, and pace
5. ✅ Compare against the market line you enter
6. ✅ Show edge, Kelly sizing, and confidence level
7. ✅ Display a **bet recommendation** with signal tier (🔥 Strong / 📊 Lean / 📉 Low Edge / 🚨 Extreme)
8. ✅ Prompt for **Pick** (accept recommendation or override), **Bet Type** (Spread/ML/O-U), **Sportsbook**, **Odds**, and **Bet amount**
9. ✅ Auto-calculate **ToWin** from your odds and stake
10. ✅ Auto-record **Timestamp** and **Confidence** grade
11. ✅ Log everything to `bet_tracker_YYYY-MM-DD.csv`

**Dashboard Example:**

```
📡 Source: ESPN
G1  Cleveland Cavaliers    @ Charlotte Hornets      7:00 PM  🎫
G2  Indiana Pacers         @ Washington Wizards     7:00 PM  🎫
G3  Utah Jazz              @ Memphis Grizzlies      7:00 PM  🎫
G4  Miami Heat             @ Atlanta Hawks           7:30 PM  🎫
G5  Dallas Mavericks       @ Minnesota Timberwolves  7:30 PM
G6  Milwaukee Bucks        @ New Orleans Pelicans    8:00 PM
G7  Brooklyn Nets          @ Oklahoma City Thunder   8:00 PM
G8  Los Angeles Clippers   @ Los Angeles Lakers     10:00 PM
G9  Denver Nuggets         @ Portland Trail Blazers 10:00 PM
  🎫 = Bet placed (4/9 games)

  📈 7:00 PM (G1, G2, G3): CLV ⚠️  Fetched 10h ago
     → Run at ~6:45 PM: ./fetch_all_nba_data.sh odds,injuries
  📈 7:30 PM (G4, G5): CLV ⚠️  Fetched 10h ago
     → Run at ~7:15 PM: ./fetch_all_nba_data.sh odds,injuries
  📈 8:00 PM (G6, G7): CLV ⚠️  Fetched 10h ago
     → Run at ~7:45 PM: ./fetch_all_nba_data.sh odds,injuries
  📈 10:00 PM (G8, G9): CLV ⚠️  Fetched 10h ago
     → Run at ~9:45 PM: ./fetch_all_nba_data.sh odds,injuries
```

**What the dashboard tells you:**

| Indicator             | Meaning                                                                                |
| --------------------- | -------------------------------------------------------------------------------------- |
| 🎫 (next to game)     | You already have a bet logged for this game                                            |
| 🎫 = Bet placed (N/M) | N of M total games have bets — quickly see what's left                                 |
| CLV ✅ Fresh          | Odds were fetched within 30 min of this window's tip-off — closing lines are locked in |
| CLV ⚠️ Fetched Xh ago | Odds are stale for this window — run the suggested command before tip-off              |
| CLV ❌ Not fetched    | No odds cached at all — you'll miss CLV data without a fetch                           |
| → Run at ~TIME        | The exact time to run `./fetch_all_nba_data.sh odds,injuries` (15 min before tip)      |

**Additional Commands:**

| Command | Action                                                                                             |
| ------- | -------------------------------------------------------------------------------------------------- |
| `G#`    | Analyze a today's game (e.g., `G1`, `G5`) — full analysis + bet logging                            |
| `U`     | Browse upcoming games for the next 7 days (loops back after each analysis; `Q` to exit)            |
| `U#`    | Analyze an upcoming game (e.g., `U1`, `U12`) — **preview mode**, no bet logging                    |
| `B`     | View bet tracker history — select a day or all combined, see P&L summary (loops back; `Q` to exit) |
| `P`     | Pre-Tipoff Review — compare fresh data against placed bets (injuries, line movement, action recs)  |
| `C`     | Custom matchup — enter any two teams for analysis                                                  |
| `R`     | Refresh all data caches (stats, injuries, news, rest, odds)                                        |
| `Q`     | Quit                                                                                               |

### 3. After Games — Update Results

```bash
python update_results.py
```

Auto-fetches final scores from the NBA API and fills in WIN/LOSS/PUSH + Payout. Also populates **ClosingLine** and **CLV** (Closing Line Value) from cached odds — see CLV section below.

### 4. Analyze Performance

```bash
python post_mortem.py
```

Menu-driven analyzer with 5 options:

- **[1] Single-Day Post-Mortem** — win/loss/push breakdown with injury & margin analysis
- **[2] Lifetime Dashboard** — all-time record, ROI, CLV summary, streaks, 6-point pro-level verdict
- **[3] Edge Calibration** — do bigger edges win at higher rates?
- **[4] Daily Trend & Profit Curve** — cumulative P/L with ASCII chart
- **[5] Bankroll Tracker** — real-dollar bankroll tracking with Kelly sizing

---

## 🏥 Injury Data

Injury data is auto-scraped by `injury_scraper.py` (run via `fetch_all_nba_data.sh`) and cached to `nba_injuries.csv`.

The engine automatically adjusts fair lines based on injury impact:

- **Star players** (Jokic, Luka, LeBron, etc.): 8–12 points impact
- **Good starters**: 5–8 points impact
- **Role players**: 2–3 points impact

Status levels: `out` (100%), `doubtful` (80%), `day-to-day` (50%), `questionable` (40%), `probable` (10%)

---

## 📅 Rest & Fatigue

Rest penalty data is auto-scraped by `rest_penalty_scraper.py` and cached to `nba_rest_penalty_cache.csv`.

- **Back-to-back**: −2.5 points (team on B2B loses edge)
- **Extra rest**: +0.3 to +0.5 per day (diminishing returns)

---

## 💰 Bet Tracking & Real Money

When logging a bet in the engine UI, you'll be prompted for:

| Field      | Example      | Notes                                               |
| ---------- | ------------ | --------------------------------------------------- |
| Pick       | `Bucks`      | Defaults to engine recommendation; type to override |
| Bet Type   | `S`          | S=Spread (default), M=Moneyline, O=Over/Under       |
| Sportsbook | `DraftKings` | Optional — press Enter to skip                      |
| Odds       | `-110`       | American odds — optional                            |
| Bet amount | `50`         | Dollar amount — optional                            |

These are saved in the bet tracker CSV along with auto-recorded **Timestamp**, **Confidence** grade, and **ToWin** (calculated from odds × stake). When `update_results.py` populates WIN/LOSS, it auto-calculates the **Payout** column:

- **WIN at -110**: Bet $50 → Payout +$45.45 (profit)
- **LOSS**: Bet $50 → Payout -$50.00
- **PUSH** (spread tie): Bet $50 → Payout $0.00 (money returned)

The post-mortem's **Lifetime Dashboard** and **Bankroll Tracker** use this data for real-dollar P/L and sportsbook-level breakdowns.

> **Preview Mode:** Upcoming games (`U#`) run in preview mode — full analysis is displayed but nothing is logged to the bet tracker. This protects you from logging bets with stale data. Re-analyze on game day with `G#` to log.

---

## 📒 Viewing Bet History

Use the `[B]` command inside the engine UI to review your betting history without leaving the app.

1. Lists all `bet_tracker_*.csv` files with bet counts
2. Select a tracker by number, or `A` to view all combined
3. Displays a formatted table with: matchup, pick, edge, odds, bet amount, result (✅/❌/⏳), payout, and notes
4. Shows a **P&L summary**: record, win rate, total wagered, net profit/loss, and ROI
5. Loops back to the tracker list so you can pick another — press `Q` or Enter to return to the main menu

The combined view prefixes each bet ID with the tracker date (e.g., `2026-02-11/G3`) for easy cross-referencing.

---

## 💵 Bankroll Management

Run `python post_mortem.py` → option **[5] Bankroll Tracker**.

On first run, you'll set:

- **Starting bankroll** (e.g., $1,000)
- **Unit size** (default = bankroll / 100)
- **Edge cap** (default = 10 pts — edges above this are capped and flagged as suspicious)

The tracker then shows day-by-day balance changes using real bet data (when available) or flat-unit estimates. It also provides **Quarter-Kelly recommended bet sizing** based on your lifetime win rate.

**Ready to scale up?** Press `[R]` in the bankroll tracker to reset your starting bankroll, unit size, and edge cap at any time.

### Edge Cap Audit

The Lifetime Dashboard (`post_mortem.py` → [2]) includes an **Edge Cap Audit** that compares capped vs. uncapped bet performance:

- **Capped vs. uncapped win rates** — are flagged bets dragging down your record?
- **Raw edge distribution** — how extreme are the capped edges?
- **Recommendation** — after 5+ decided capped bets, the system suggests whether to keep, raise, or lower the cap

The CSV stores both `Raw_Edge` (uncapped) and `Edge_Capped` (YES/NO). Historical bets without these columns are reconstructed from `abs(Fair - Market)`.

---

## ⚠️ Checking for Late Scratches (30 mins before tipoff)

```bash
python nba_lineup_and_news_monitor.py
```

This monitors ESPN and NBA.com headlines for injury/scratch alerts.

**Manual verification (more reliable):**

1. ✅ Check team warm-up videos on NBA.com or ESPN
2. ✅ Look for starting lineup confirmations
3. ✅ Check team official Twitter/X
4. ✅ Review betting line movements (sharp money often signals scratches)

**Key indicators of a late scratch:**

- Line movement of 1+ point in last hour
- Official "questionable" player ruled out

---

## 📈 Closing Line Value (CLV)

CLV measures whether you got a better number than the final market consensus at tip-off. It's the gold standard for proving real betting edge.

**How it works:**

1. `fetch_all_nba_data.sh odds` caches live spreads from 15+ sportsbooks (via The Odds API)
2. You place your bet and the engine records your **Market Line**
3. After games finish, `update_results.py` compares your line to the cached **Closing Line**
4. **CLV = Closing Line − Your Market Line** → positive means you beat the market

**Pre-Tipoff CLV Workflow:**

To capture the best closing lines, run the odds-only fetch **as close to tip-off as possible**:

| Scenario                  | Command                                 | When to run                |
| ------------------------- | --------------------------------------- | -------------------------- |
| Full morning refresh      | `./fetch_all_nba_data.sh`               | Morning (all feeds)        |
| Pre-tipoff odds snapshot  | `./fetch_all_nba_data.sh odds`          | 10–15 min before first tip |
| Late scratch + odds combo | `./fetch_all_nba_data.sh odds,injuries` | 10–15 min before first tip |
| Late-window games only    | `./fetch_all_nba_data.sh odds`          | 10–15 min before late tips |

For split slates (e.g., 7 PM ET + 10 PM ET tips), run `./fetch_all_nba_data.sh odds` twice — once before the early window and once before the late window — to get the tightest closing lines for each group.

**You don't need to memorize this.** The engine dashboard automatically groups games by tip-off window and shows the exact time to run each fetch, with live CLV freshness status per window. Just follow the `→ Run at ~TIME` prompts.

**Setup:** Copy `.env.example` to `.env` and add your free API key from [the-odds-api.com](https://the-odds-api.com). The engine works without it — CLV columns will simply be blank.

**Why it matters:** Bettors who consistently beat the closing line are profitable long-term, regardless of short-term variance. Sportsbooks don't provide this metric — they use it internally to identify and limit sharp accounts.

---

## ⚡ Betting Decision Flow

```
  ── MORNING ──────────────────────────────────────────────
  1. RUN: ./fetch_all_nba_data.sh          (all feeds)
     ↓
  2. RUN: python nba_engine_ui.py
     ↓
  3. Browse upcoming games with [U] — scout early
     ↓
  4. Review HIGH EDGE games (5+ points, HIGH confidence)
     ↓
  5. Enter market line → get recommendation
     ↓
  6. Enter sportsbook, odds, bet amount

  ── PRE-TIPOFF (10-15 min before first tip) ─────────────
  7. RUN: ./fetch_all_nba_data.sh odds,injuries (CLV + late scratches)
     ↓
  8. RUN: [P] Pre-Tipoff Review in engine UI
     → Shows injury changes, line movement, updated edge
     → Action per bet: 🟢 HOLD / 🟡 REVIEW / 🔴 HEDGE
     ↓
  9. Act on recommendations — hold, hedge, or cash out
     ↓
 10. Place any new bets at your sportsbook

  ── LATE WINDOW (if split slate, e.g. 10 PM tips) ──────
 11. RUN: ./fetch_all_nba_data.sh odds     (2nd CLV snapshot)

  ── AFTER GAMES ─────────────────────────────────────────
 12. RUN: python update_results.py         (scores + CLV)
     ↓
 13. Review with [B] in engine or python post_mortem.py
```

---

## 📝 Key Files

| File                         | Purpose                       | Update Frequency                   |
| ---------------------------- | ----------------------------- | ---------------------------------- |
| `nba_injuries.csv`           | Player injury status          | `./fetch_all_nba_data.sh injuries` |
| `nba_rest_penalty_cache.csv` | Rest/fatigue penalties        | `./fetch_all_nba_data.sh rest`     |
| `nba_stats_cache.json`       | Team efficiency ratings       | `./fetch_all_nba_data.sh stats`    |
| `odds_cache.json`            | Live spreads for CLV tracking | `./fetch_all_nba_data.sh odds`     |
| `bet_tracker_YYYY-MM-DD.csv` | Bets + results + CLV + real $ | Daily                              |
| `schedule_scraper.py`        | Multi-source schedule tool    | On demand                          |
| `bankroll.json`              | Bankroll config               | Set once, auto-maintained          |
| `.env`                       | API keys (Odds API)           | Set once                           |
| `text_to_image.py`           | Terminal → PNG screenshot     | On demand                          |

---

## 🎯 Your Competitive Edge

This system factors in:

- ✅ Team offensive/defensive efficiency
- ✅ Home court advantage
- ✅ Pace of play
- ✅ **Player injuries and star impact** ← Most sportsbooks are slow to adjust
- ✅ **Rest days and B2B penalties** ← Sharp bettors track this
- ✅ **Late scratch monitoring** ← Key for real-time
- ✅ **CLV tracking** ← Proves real edge vs. just running hot
- ✅ **Real-money P/L tracking** ← Know exactly where you stand

**Pro benchmark: >52.4% ATS win rate = profitable at -110 vig.**

---

## 💡 Tips & Tricks

1. **Only bet HIGH-SIGNAL games** — Edge ≥ 5 with HIGH confidence
2. **Use Quarter-Kelly sizing** — never risk more than the bankroll tracker recommends
3. **Full refresh in the morning** — run `./fetch_all_nba_data.sh` (all feeds) once per session
4. **Watch warm-ups** — subtle signs of player issues appear during shootaround
5. **Monitor line movements** — if line moves 1+ point, something changed
6. **Track everything** — enter Book, Odds, and Bet for real-dollar accountability (ToWin is auto-calculated)
7. **Fetch odds before tip-off** — run `./fetch_all_nba_data.sh odds` 10–15 min before tip to cache closing lines for CLV (run twice for split slates)
8. **Late scratch check** — run `./fetch_all_nba_data.sh injuries` or `./fetch_all_nba_data.sh odds,injuries` pre-tip to catch last-minute lineup changes
9. **Review post-mortem weekly** — check if model edge and CLV are holding up

---

**You're now ready to place informed bets with full performance tracking! 🎯**
