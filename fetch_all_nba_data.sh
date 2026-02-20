#!/bin/bash
# Unified script to fetch and cache all NBA data for robust offline operation
# Runs all fetchers and caches their outputs

set -euo pipefail
cd "$(dirname "$0")"

# Activate virtual environment if present, otherwise use python3
if [ -f .venv/bin/activate ]; then
  source .venv/bin/activate
elif ! command -v python &> /dev/null; then
  alias python=python3
fi

LOG=fetch_all_nba_data.log
> "$LOG"

run_fetcher() {
  local script="$1"
  echo "[INFO] Running $script..." | tee -a "$LOG"
  if python "$script" >> "$LOG" 2>&1; then
    echo "[SUCCESS] $script completed." | tee -a "$LOG"
  else
    echo "[ERROR] $script failed. Check $LOG for details." | tee -a "$LOG"
    exit 1
  fi
}

# Fetch NBA team advanced stats
run_fetcher nba_data_fetcher_advanced.py

# Fetch and cache injury data
run_fetcher injury_scraper.py

run_fetcher nba_lineup_and_news_monitor.py

run_fetcher rest_penalty_scraper.py

# Fetch and cache NBA news for offline use
echo "[INFO] Caching NBA news..." | tee -a "$LOG"
if python cache_nba_news.py >> "$LOG" 2>&1; then
  echo "[SUCCESS] NBA news cached." | tee -a "$LOG"
else
  echo "[ERROR] NBA news cache failed. Check $LOG for details." | tee -a "$LOG"
  exit 1
fi

# Prefetch NBA schedule (today + 7 days) for fully offline UI
run_fetcher schedule_prefetch.py

# Prefetch star tax (On/Off plus-minus) for all teams
run_fetcher star_tax_prefetch.py

# Fetch and cache live odds for CLV tracking (non-fatal if no games)
echo "[INFO] Fetching NBA odds for CLV tracking..." | tee -a "$LOG"
if python odds_api.py >> "$LOG" 2>&1; then
  echo "[SUCCESS] NBA odds fetched." | tee -a "$LOG"
else
  echo "[WARN] Odds fetch failed (non-fatal — may be no games today)." | tee -a "$LOG"
fi

# Final check for all caches
if [ -s nba_stats_cache.json ] && [ -s nba_injuries.csv ] && [ -s nba_news_cache.json ] && [ -s nba_rest_penalty_cache.csv ] && [ -s nba_schedule_cache.json ] && [ -s nba_star_tax_cache.json ]; then
  echo "" | tee -a "$LOG"
  echo "[SUMMARY] NBA Data Fetch Counts:" | tee -a "$LOG"
  # Parse counts from log
  STATS_COUNT=$(grep -Eo 'Scraped [0-9]+ teams' "$LOG" | grep -Eo '[0-9]+' | tail -1 || true)
  INJURY_COUNT=$(grep -Eo 'Saved injury data to nba_injuries.csv with [0-9]+ records' "$LOG" | grep -Eo '[0-9]+' | tail -1 || true)
  REST_COUNT=$(grep -Eo 'Cached rest penalty data for [0-9]+ teams' "$LOG" | grep -Eo '[0-9]+' | tail -1 || true)
  NEWS_COUNT=$(grep -Eo 'Cached [0-9]+ NBA news items' "$LOG" | grep -Eo '[0-9]+' | tail -1 || true)
  ODDS_COUNT=$(grep -Eo 'Fetched [0-9]+ game' "$LOG" | grep -Eo '[0-9]+' | tail -1 || true)
  echo "  - NBA Team Stats: ${STATS_COUNT:-0} teams (NBA.com)" | tee -a "$LOG"
  echo "  - Injuries: ${INJURY_COUNT:-0} records (CBS Sports)" | tee -a "$LOG"
  echo "  - Rest Penalty: ${REST_COUNT:-0} teams (ESPN)" | tee -a "$LOG"
  echo "  - NBA News: ${NEWS_COUNT:-0} items (ESPN)" | tee -a "$LOG"
  SCHED_COUNT=$(grep -Eo 'Cached [0-9]+ total games' "$LOG" | grep -Eo '[0-9]+' | tail -1 || true)
  STAR_TAX_COUNT=$(grep -Eo 'Cached star tax data for [0-9]+ teams' "$LOG" | grep -Eo '[0-9]+' | tail -1 || true)
  echo "  - Odds (CLV): ${ODDS_COUNT:-0} games (The Odds API)" | tee -a "$LOG"
  echo "  - Schedule: ${SCHED_COUNT:-0} games (ESPN)" | tee -a "$LOG"
  echo "  - Star Tax: ${STAR_TAX_COUNT:-0} teams (NBA.com)" | tee -a "$LOG"
  echo "" | tee -a "$LOG"
  echo "[COMPLETE] All NBA data cached successfully. Now run: python nba_engine_ui.py." | tee -a "$LOG"
else
  echo "[FATAL] One or more caches missing or empty. Data fetch failed." | tee -a "$LOG"
  exit 2
fi
