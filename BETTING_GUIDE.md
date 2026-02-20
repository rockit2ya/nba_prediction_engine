# How to Use Your Enhanced NBA Betting Engine

## Quick Start — Place Bets Tonight

### 1. Fetch Fresh Data

```bash
./fetch_all_nba_data.sh
```

This runs all scrapers (team stats, injuries, rest penalties, news, and live odds) and caches the results locally.

### 2. Run the Prediction Engine

```bash
python nba_engine_ui.py
```

The interactive UI will:

1. ✅ Display today's NBA games (ScoreboardV2 primary, ESPN scrape fallback)
2. ✅ Let you select a matchup to analyze
3. ✅ Calculate fair lines from team efficiency, injuries, rest, and pace
4. ✅ Compare against the market line you enter
5. ✅ Show edge, Kelly sizing, and confidence level
6. ✅ Display a **bet recommendation** with signal tier (🔥 Strong / 📊 Lean / 📉 Low Edge / 🚨 Extreme)
7. ✅ Prompt for **Pick** (accept recommendation or override), **Bet Type** (Spread/ML/O-U), **Sportsbook**, **Odds**, and **Bet amount**
8. ✅ Auto-calculate **ToWin** from your odds and stake
9. ✅ Auto-record **Timestamp** and **Confidence** grade
10. ✅ Log everything to `bet_tracker_YYYY-MM-DD.csv`

**Additional Commands:**

| Command | Action |
| ------- | ------ |
| `G#`    | Analyze a today's game (e.g., `G1`, `G5`) — full analysis + bet logging |
| `U`     | Browse upcoming games for the next 7 days (loops back after each analysis; `Q` to exit) |
| `U#`    | Analyze an upcoming game (e.g., `U1`, `U12`) — **preview mode**, no bet logging |
| `B`     | View bet tracker history — select a day or all combined, see P&L summary (loops back; `Q` to exit) |
| `C`     | Custom matchup — enter any two teams for analysis |
| `R`     | Refresh all data caches (stats, injuries, news, rest, odds) |
| `Q`     | Quit |

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

1. `fetch_all_nba_data.sh` caches live spreads from 15+ sportsbooks (via The Odds API)
2. You place your bet and the engine records your **Market Line**
3. After games finish, `update_results.py` compares your line to the cached **Closing Line**
4. **CLV = Closing Line − Your Market Line** → positive means you beat the market

**Setup:** Copy `.env.example` to `.env` and add your free API key from [the-odds-api.com](https://the-odds-api.com). The engine works without it — CLV columns will simply be blank.

**Why it matters:** Bettors who consistently beat the closing line are profitable long-term, regardless of short-term variance. Sportsbooks don't provide this metric — they use it internally to identify and limit sharp accounts.

---

## ⚡ Betting Decision Flow

```
1. RUN: fetch_all_nba_data.sh (fresh data)
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
   ↓
7. Verify warm-ups 30 mins before game
   ↓
8. Check for late scratches
   ↓
9. Place bets at your sportsbook
   ↓
10. RUN: python update_results.py (after games)
    ↓
11. Review with [B] in engine or python post_mortem.py
```

---

## 📝 Key Files

| File                         | Purpose                       | Update Frequency          |
| ---------------------------- | ----------------------------- | ------------------------- |
| `nba_injuries.csv`           | Player injury status          | Auto-scraped each run     |
| `nba_rest_penalty_cache.csv` | Rest/fatigue penalties        | Auto-scraped each run     |
| `nba_stats_cache.json`       | Team efficiency ratings       | Auto-fetched each run     |
| `odds_cache.json`            | Live spreads for CLV tracking | Auto-fetched each run     |
| `bet_tracker_YYYY-MM-DD.csv` | Bets + results + CLV + real $ | Daily                     |
| `schedule_scraper.py`        | Multi-source schedule tool    | On demand                 |
| `bankroll.json`              | Bankroll config               | Set once, auto-maintained |
| `.env`                       | API keys (Odds API)           | Set once                  |
| `text_to_image.py`           | Terminal → PNG screenshot     | On demand                 |

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
3. **Update injuries before each session** — run `fetch_all_nba_data.sh`
4. **Watch warm-ups** — subtle signs of player issues appear during shootaround
5. **Monitor line movements** — if line moves 1+ point, something changed
6. **Track everything** — enter Book, Odds, and Bet for real-dollar accountability (ToWin is auto-calculated)
7. **Fetch odds before tip-off** — run `fetch_all_nba_data.sh` close to game time to cache the best closing lines for CLV
8. **Review post-mortem weekly** — check if model edge and CLV are holding up

---

**You're now ready to place informed bets with full performance tracking! 🎯**
