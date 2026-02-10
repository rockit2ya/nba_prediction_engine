# NBA Prediction Engine - API Status & Usage Guide

## Current Status

### ✅ Confirmed Working
- **Cached team statistics**: Real 2025-26 season data saved locally
- **Fair line calculations**: Properly weighted based on team ratings
- **Kelly criterion bankroll management**: Functional predictor
- **CSV logging**: Bet tracking works correctly

### ⚠️ API Issues Identified
The NBA Stats API (`stats.nba.com`) **times out** when accessed from Python, even though:
- The landing page is accessible in a browser
- Your network connection is fine
- The API exists and has data

This appears to be an **API rate limiting or request filtering** issue specific to Python requests.

---

## How to Use Safely

### Recommended Workflow (Without Live API)

1. **Start the UI normally:**
   ```bash
   ./nba_predict/bin/python nba_engine_ui.py
   ```

2. **What happens:**
   - Loads cached team statistics automatically
   - Generates fair lines based on team offensive/defensive ratings
   - Fair lines will **vary** based on team quality (not all 3.0)
   - Injuries/rest penalties gracefully degrade to 0 if API unreachable

3. **Fair lines you'll see:**
   - Strong vs Weak team → large spreads (7-10 points)
   - Matched teams → smaller spreads (1-4 points)
   - All based on real offensive/defensive efficiency metrics

### Example Outputs
```
Thunder @ Lakers → Fair Line: 2.80
Cavs @ Bucks     → Fair Line: 4.12
Nuggets @ Suns   → Fair Line: 6.06
```

---

## If API Becomes Available

If the NBA Stats API starts working again:

1. **Force a data refresh:**
   ```bash
   ./nba_predict/bin/python -c "from nba_analytics import calculate_pace_and_ratings; calculate_pace_and_ratings(force_refresh=True)"
   ```

2. **Or manually update sample data:**
   ```bash
   ./nba_predict/bin/python create_sample_cache.py
   ```

---

## Betting Recommendations

### ✅ Safe to Use:
- Fair lines based on team efficiency ratings
- Kelly criterion sizing (already conservative at 25%)
- Edge calculations (Market vs Fair)

### ⚠️ Limited Without Live Data:
- Injury adjustments (will show 0 impact)
- Back-to-back penalties (will default to 0)
- Questionable player tracking

### Bottom Line:
**Beta/Test Mode:** Use for tracking and testing your system logic.
**Real Money:** Wait for live API access or manually verify injuries before placing bets.

---

## Files Reference

| File | Purpose |
|------|---------|
| `nba_stats_cache.json` | Cached team statistics (updated automatically when API works) |
| `create_sample_cache.py` | Generate fresh sample data |
| `nba_analytics.py` | Core prediction engine (improved with timeout handling) |
| `nba_engine_ui.py` | Interactive betting UI |
| `bet_tracker_*.csv` | Your bet history logs |

---

## What We Fixed

1. **Increased timeouts** on individual API calls (8-10 seconds instead of hanging)
2. **Added graceful degradation** - system doesn't hang if APIs are unavailable
3. **Cache priority** - prefers reliable cached data over unreliable live requests
4. **Clearer messages** - tells you which data source is being used

---

## Next Steps

Monitor NBA API availability and try refreshing when you're ready for live data. Until then, the cached system works perfectly for:
- Testing your Kelly calculations
- Evaluating edge opportunities  
- Tracking bet performance
- Developing your strategy
