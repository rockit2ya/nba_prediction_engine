# How to Use Your Enhanced NBA Betting Engine

## Quick Start - **Place Bets Tonight**

Run this command to get final recommended fair lines with injuries & rest factored in:

```bash
./nba_predict/bin/python final_bet_calc.py
```

This will:
1. ✅ Load your tonight's games from `bet_tracker_2026-02-09.csv`
2. ✅ Calculate base fair lines from team efficiency
3. ✅ Apply injury impact adjustments
4. ✅ Apply rest day advantages/penalties
5. ✅ Update the CSV with final fair lines, edges, and Kelly percentages

**Output shows:**
- **Base**: Fair line from team stats alone
- **Adj**: Adjusted fair line (with injuries + rest)
- **Market**: Your market line
- **Edge**: How much value (difference between fair and market)
- **Kelly**: Conservative (25%) position sizing

---

## 🏥 Adding Injury Data

Your system reads injury data from **`injuries_manual.csv`**

### How to Update:

1. **Check latest injury reports** from:
   - NBA.com/status (official)
   - ESPN NBA injuries page
   - Team official social media
   - Your sportsbook's injury updates

2. **Update `injuries_manual.csv`:**
   ```csv
   Team,Player,Status,Notes,DateUpdated
   Los Angeles Lakers,LeBron James,out,Ankle soreness,2026-02-09
   Denver Nuggets,Jamal Murray,questionable,Finger injury,2026-02-09
   ```

3. **Status options:**
   - `out` - Full impact (100% adjustment)
   - `doubtful` - High impact (80%)
   - `day-to-day` - Moderate impact (50%)
   - `questionable` - Lower impact (40%)
   - `probable` - Minimal impact (10%)

4. **Run calculator again:**
   ```bash
   ./nba_predict/bin/python final_bet_calc.py
   ```

### Impact Calculation:
- **Star players** (Jokic, Luka, LeBron, etc.): 8-12 points impact
- **Good players**: 5-8 points impact  
- **Role players**: 2-3 points impact

---

## 📅 Updating Rest Days

Your system reads rest schedule from **`game_schedule.csv`**

### How to Update:

1. **Before games start**, update the most recent game dates:
   ```csv
   Team,LastGameDate,LastGameOpponent,Notes
   Oklahoma City Thunder,2026-02-08,Denver Nuggets,Regular game
   Los Angeles Lakers,2026-02-06,Golden State Warriors,2 days rest
   ```

2. **How to find last game dates:**
   - ESPN schedule (team page)
   - NBA.com schedule
   - Your sports stats site

3. **Note B2B situations:**
   - If team played yesterday → `LastGameDate: 2026-02-08`
   - If team played 2 days ago → `LastGameDate: 2026-02-07`

4. **Impact calculation:**
   - **Back-to-back**: -2.5 points (team on B2B loses edge)
   - **Extra rest**: +0.3 to +0.5 per day (diminishing returns)

---

## ⚠️ Checking for Late Scratches (30 mins before tipoff)

### Option 1: Automated Check
```bash
./nba_predict/bin/python late_scratch_checker.py
```
This searches ESPN and NBA.com headlines for injury/scratch alerts.

### Option 2: Manual Verification (More Reliable)

**30 minutes before tipoff, verify:**
1. ✅ Check team warm-up videos on NBA.com or ESPN
2. ✅ Look for starting lineup confirmations
3. ✅ Check team official Twitter/X (@[TeamName])
4. ✅ Review betting line movements (sharp money often signals scratches)
5. ✅ Check if star players are at arena

**Key indicators of a late scratch:**
- Line movement of 1+ point in last hour
- Team scoring average drops 5+ points
- Official "questionable" player ruled out

---

## 📊 Understanding Your Updated Bets

### Example: Thunder @ Lakers

**Original (No Adjustments):**
- Base Fair: 2.80 (Thunder slightly favored)

**With LeBron Injury:**
- Injury adjustment: -1.60 (LeBron's impact)
- Adjusted Fair: 1.20 (Lakers more favored now)

**Result:**
- If market is -6.5 (LA favored by 6.5)
- Your edge: 5.30 points
- Kelly recommendation: 4.19% of bankroll

---

## 🚀 Advanced Usage

### For Detailed Injury Analysis:
```bash
./nba_predict/bin/python enhanced_bet_calculator.py
```
Shows individual player impacts and warnings.

### For Manual Edge Checking:
```bash
./nba_predict/bin/python test_fair_lines.py
```
Quick verification without API calls.

### For Latest Injury News:
```bash
./nba_predict/bin/python injury_scraper.py
```
Attempts to scrape ESPN/NBA for latest updates (5-second timeout).

---

## ⚡ Betting Decision Flow

```
1. RUN: final_bet_calc.py
   ↓
2. Review HIGH EDGE games (5+ points)
   ↓
3. Check injuries_manual.csv for latest
   ↓
4. Update game_schedule.csv with rest days
   ↓
5. Verify warm-ups 30 mins before game
   ↓
6. Check for late scratches
   ↓
7. Place bets at your sportsbook
   ↓
8. Track results in CSV
```

---

## 📝 Template Files to Maintain

| File | Purpose | Update Frequency |
|------|---------|-----------------|
| `injuries_manual.csv` | Player injury status | Before each analysis |
| `game_schedule.csv` | Last game dates (rest) | Before each analysis |
| `bet_tracker_YYYY-MM-DD.csv` | Tonight's bets + results | Daily |
| `nba_stats_cache.json` | Team efficiency ratings | 1-2x per week |

---

## 🎯 Your Competitive Edge

This system factors in:
- ✅ Team offensive/defensive efficiency
- ✅ Home court advantage
- ✅ Pace of play
- ✅ **Player injuries and star impact** ← Most sportsbooks ignore
- ✅ **Rest days and B2B penalties** ← Sharp bettors track
- ✅ **Late scratch monitoring** ← Key for real-time

**Most casual bettors only use team name + line. You have 3 additional factors.**

---

## 💡 Tips & Tricks

1. **Update injuries first thing in morning** - Most scratches announced early
2. **Trust high-edge games** (5+ points) - Only bet these
3. **Watch warm-ups** - Subtle signs of player issues appear during shootaround
4. **Monitor line movements** - If line moves 1+ point, something changed (injury)
5. **Keep historical notes** - Track why predictions miss (hidden injuries, etc.)

---

## ⚙️ System Maintenance

Every week:
```bash
# Refresh team efficiency stats (if NBA API works)
./nba_predict/bin/python create_sample_cache.py

# Update injury file with past week's trend
# (Check which injuries became more/less serious)

# Archive old bet trackers
mv bet_tracker_2026-02-*.csv archive/
```

---

**You're now ready to place informed bets with injury intelligence! 🎯**
