# How to Use Your Enhanced NBA Betting Engine

## Quick Start — Place Bets Tonight

### 1. Fetch Fresh Data

```bash
./fetch_all_nba_data.sh
```

This runs all scrapers (team stats, injuries, rest penalties, news) and caches the results locally.

### 2. Run the Prediction Engine

```bash
python nba_engine_ui.py
```

The interactive UI will:
1. ✅ Display today's NBA games
2. ✅ Let you select a matchup to analyze
3. ✅ Calculate fair lines from team efficiency, injuries, rest, and pace
4. ✅ Compare against the market line you enter
5. ✅ Show edge, Kelly sizing, and confidence level
6. ✅ Prompt for **Sportsbook**, **Odds**, and **Bet amount** (all optional)
7. ✅ Log everything to `bet_tracker_YYYY-MM-DD.csv`

### 3. After Games — Update Results

```bash
python update_results.py
```

Auto-fetches final scores from the NBA API and fills in WIN/LOSS + Payout.

### 4. Analyze Performance

```bash
python post_mortem.py
```

Menu-driven analyzer with 5 options:
- **[1] Single-Day Post-Mortem** — win/loss breakdown with injury & margin analysis
- **[2] Lifetime Dashboard** — all-time record, ROI, streaks, pro-level verdict
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

| Field | Example | Notes |
|-------|---------|-------|
| Sportsbook | `DraftKings` | Optional — press Enter to skip |
| Odds | `-110` | American odds — optional |
| Bet amount | `50` | Dollar amount — optional |

These are saved in the bet tracker CSV. When `update_results.py` populates WIN/LOSS, it auto-calculates the **Payout** column:
- **WIN at -110**: Bet $50 → Payout +$45.45 (profit)
- **LOSS**: Bet $50 → Payout -$50.00

The post-mortem's **Lifetime Dashboard** and **Bankroll Tracker** use this data for real-dollar P/L and sportsbook-level breakdowns.

---

## 💵 Bankroll Management

Run `python post_mortem.py` → option **[5] Bankroll Tracker**.

On first run, you'll set:
- **Starting bankroll** (e.g., $1,000)
- **Unit size** (default = bankroll / 100)

The tracker then shows day-by-day balance changes using real bet data (when available) or flat-unit estimates. It also provides **Quarter-Kelly recommended bet sizing** based on your lifetime win rate.

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

## ⚡ Betting Decision Flow

```
1. RUN: fetch_all_nba_data.sh (fresh data)
   ↓
2. RUN: python nba_engine_ui.py
   ↓
3. Review HIGH EDGE games (5+ points, HIGH confidence)
   ↓
4. Enter market line → get recommendation
   ↓
5. Enter sportsbook, odds, bet amount
   ↓
6. Verify warm-ups 30 mins before game
   ↓
7. Check for late scratches
   ↓
8. Place bets at your sportsbook
   ↓
9. RUN: python update_results.py (after games)
   ↓
10. RUN: python post_mortem.py (analyze performance)
```

---

## 📝 Key Files

| File | Purpose | Update Frequency |
|------|---------|-----------------|
| `nba_injuries.csv` | Player injury status | Auto-scraped each run |
| `nba_rest_penalty_cache.csv` | Rest/fatigue penalties | Auto-scraped each run |
| `nba_stats_cache.json` | Team efficiency ratings | Auto-fetched each run |
| `bet_tracker_YYYY-MM-DD.csv` | Bets + results + real $ | Daily |
| `bankroll.json` | Bankroll config | Set once, auto-maintained |

---

## 🎯 Your Competitive Edge

This system factors in:
- ✅ Team offensive/defensive efficiency
- ✅ Home court advantage
- ✅ Pace of play
- ✅ **Player injuries and star impact** ← Most sportsbooks are slow to adjust
- ✅ **Rest days and B2B penalties** ← Sharp bettors track this
- ✅ **Late scratch monitoring** ← Key for real-time
- ✅ **Real-money P/L tracking** ← Know exactly where you stand

**Pro benchmark: >52.4% ATS win rate = profitable at -110 vig.**

---

## 💡 Tips & Tricks

1. **Only bet HIGH-SIGNAL games** — Edge ≥ 5 with HIGH confidence
2. **Use Quarter-Kelly sizing** — never risk more than the bankroll tracker recommends
3. **Update injuries before each session** — run `fetch_all_nba_data.sh`
4. **Watch warm-ups** — subtle signs of player issues appear during shootaround
5. **Monitor line movements** — if line moves 1+ point, something changed
6. **Track everything** — enter Book, Odds, and Bet for real-dollar accountability
7. **Review post-mortem weekly** — check if model edge is holding up

---

**You're now ready to place informed bets with full performance tracking! 🎯**
