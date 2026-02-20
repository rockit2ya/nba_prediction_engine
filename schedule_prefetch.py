"""
NBA Schedule Prefetcher
Fetches today's + next 7 days' NBA schedules and caches to nba_schedule_cache.json.
Uses ESPN (fast) as primary, NBA.com scoreboardv3 as fallback.

Run standalone or via fetch_all_nba_data.sh:
  python schedule_prefetch.py
"""

import json
import os
import sys
from datetime import date, timedelta, datetime

from schedule_scraper import scrape_espn, scrape_nba_com, normalize_team

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'nba_schedule_cache.json')
DAYS_AHEAD = 7  # today + 7 upcoming days


def fetch_schedule_for_date(target_date):
    """Fetch games for a single date. ESPN primary, NBA.com fallback.
    Returns (games_list, source_label)."""
    # Try ESPN first (fastest, most reliable for multi-day)
    try:
        espn_games = scrape_espn(target_date)
        if espn_games:
            games = [
                {'away': g['away'], 'home': g['home'], 'time': g.get('time', '')}
                for g in espn_games
            ]
            return games, 'ESPN'
    except Exception as e:
        print(f"  [ESPN] Failed for {target_date}: {e}")

    # Fallback: NBA.com scoreboardv3
    try:
        nba_games = scrape_nba_com(target_date)
        if nba_games:
            games = [
                {'away': g['away'], 'home': g['home'], 'time': g.get('time', '')}
                for g in nba_games
            ]
            return games, 'NBA.com'
    except Exception as e:
        print(f"  [NBA.com] Failed for {target_date}: {e}")

    return [], None


def prefetch_schedules():
    """Fetch today + DAYS_AHEAD days of schedules and write to cache."""
    today = date.today()
    cache = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'dates': {}
    }

    total_games = 0
    for offset in range(0, DAYS_AHEAD + 1):
        target = today + timedelta(days=offset)
        date_key = target.isoformat()  # e.g. "2026-02-19"
        label = "today" if offset == 0 else f"+{offset}d"

        print(f"  [{label}] Fetching {target.strftime('%A %b %-d')}...", end=' ')
        games, source = fetch_schedule_for_date(target)

        cache['dates'][date_key] = {
            'games': games,
            'source': source,
        }

        count = len(games)
        total_games += count
        src_tag = f"({source})" if source else "(no games)"
        print(f"{count} games {src_tag}")

    # Write cache
    with open(CACHE_FILE, 'w') as f:
        json.dump(cache, f, indent=2)

    print(f"\nCached {total_games} total games across {DAYS_AHEAD + 1} days to {os.path.basename(CACHE_FILE)}")
    return total_games


if __name__ == '__main__':
    print("🏀 NBA Schedule Prefetcher")
    print("=" * 50)
    prefetch_schedules()
