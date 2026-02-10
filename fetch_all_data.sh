#!/bin/bash
# Robust script to fetch all required NBA data for nba_engine_ui.py
# Runs all fetchers and checks for errors, ensuring nba_stats_cache.json is created/updated

set -euo pipefail

cd "$(dirname "$0")"

LOG=fetch_all_data.log
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

# Try advanced fetcher first
run_fetcher nba_data_fetcher_advanced.py

# If nba_stats_cache.json does not exist or is empty, try playwright fetcher

# Final check
if [ ! -s nba_stats_cache.json ]; then
  echo "[FATAL] nba_stats_cache.json still missing or empty. Data fetch failed." | tee -a "$LOG"
  exit 2
else
  echo "[COMPLETE] Data fetch successful. nba_stats_cache.json is ready." | tee -a "$LOG"
fi
