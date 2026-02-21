#!/usr/bin/env python3
"""
odds_api.py — The Odds API integration for closing line tracking.

Fetches live NBA spreads from The Odds API (free tier) and caches them.
Cached odds are used as "closing lines" for CLV (Closing Line Value) calculation
when update_results.py runs after games finish.

Usage:
    python odds_api.py              # Fetch & cache current NBA spreads
    python odds_api.py --status     # Show cache status and API quota

Automatic integration:
    - fetch_all_nba_data.sh calls this to refresh odds alongside other data
    - update_results.py reads the cache to populate ClosingLine & CLV columns

API: https://the-odds-api.com (free tier: 500 requests/month)
"""

import os
import json
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

# ─── Config ───────────────────────────────────────────────────────────────────
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
API_KEY = os.getenv('ODDS_API_KEY', '')
SPORT = 'basketball_nba'
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'odds_cache.json')
BASE_URL = 'https://api.the-odds-api.com/v4'

# Mapping from Odds API team names → common nicknames used in bet tracker CSVs
ODDS_API_TO_NICKNAME = {
    'Atlanta Hawks': 'Hawks',
    'Boston Celtics': 'Celtics',
    'Brooklyn Nets': 'Nets',
    'Charlotte Hornets': 'Hornets',
    'Chicago Bulls': 'Bulls',
    'Cleveland Cavaliers': 'Cavaliers',
    'Dallas Mavericks': 'Mavericks',
    'Denver Nuggets': 'Nuggets',
    'Detroit Pistons': 'Pistons',
    'Golden State Warriors': 'Warriors',
    'Houston Rockets': 'Rockets',
    'Indiana Pacers': 'Pacers',
    'Los Angeles Clippers': 'Clippers',
    'Los Angeles Lakers': 'Lakers',
    'Memphis Grizzlies': 'Grizzlies',
    'Miami Heat': 'Heat',
    'Milwaukee Bucks': 'Bucks',
    'Minnesota Timberwolves': 'Timberwolves',
    'New Orleans Pelicans': 'Pelicans',
    'New York Knicks': 'Knicks',
    'Oklahoma City Thunder': 'Thunder',
    'Orlando Magic': 'Magic',
    'Philadelphia 76ers': '76ers',
    'Phoenix Suns': 'Suns',
    'Portland Trail Blazers': 'Trail Blazers',
    'Sacramento Kings': 'Kings',
    'San Antonio Spurs': 'Spurs',
    'Toronto Raptors': 'Raptors',
    'Utah Jazz': 'Jazz',
    'Washington Wizards': 'Wizards',
}

# Reverse mapping
NICKNAME_TO_FULL = {v: k for k, v in ODDS_API_TO_NICKNAME.items()}


def fetch_odds():
    """
    Fetch current NBA spread odds from The Odds API.
    Returns a list of game dicts with consensus closing lines.
    """
    if not API_KEY:
        print("  ❌ No ODDS_API_KEY found. Add it to .env file.")
        return None, None

    try:
        resp = requests.get(f'{BASE_URL}/sports/{SPORT}/odds/', params={
            'apiKey': API_KEY,
            'regions': 'us',
            'markets': 'spreads',
            'oddsFormat': 'american',
        }, timeout=10)
    except requests.RequestException as e:
        print(f"  ❌ API request failed: {e}")
        return None, None

    remaining = resp.headers.get('x-requests-remaining', '?')

    if resp.status_code != 200:
        error = resp.json() if resp.headers.get('content-type', '').startswith('application/json') else resp.text
        print(f"  ❌ API error ({resp.status_code}): {error}")
        return None, remaining

    data = resp.json()
    if not data:
        print("  ⚠️  No NBA games returned (may be off-season, All-Star break, or no games today).")
        return [], remaining

    games = []
    for event in data:
        game = {
            'id': event['id'],
            'commence_time': event['commence_time'],
            'home_team': event['home_team'],
            'away_team': event['away_team'],
            'home_nickname': ODDS_API_TO_NICKNAME.get(event['home_team'], event['home_team']),
            'away_nickname': ODDS_API_TO_NICKNAME.get(event['away_team'], event['away_team']),
            'spreads': {},
            'consensus_line': None,
        }

        # Extract spread from each bookmaker
        for book in event.get('bookmakers', []):
            book_name = book['title']
            for market in book.get('markets', []):
                if market['key'] != 'spreads':
                    continue
                for outcome in market.get('outcomes', []):
                    if outcome['name'] == event['home_team']:
                        game['spreads'][book_name] = outcome['point']
                        break

        # Calculate consensus (median of all book spreads)
        if game['spreads']:
            values = sorted(game['spreads'].values())
            mid = len(values) // 2
            if len(values) % 2 == 0:
                game['consensus_line'] = (values[mid - 1] + values[mid]) / 2
            else:
                game['consensus_line'] = values[mid]

        games.append(game)

    return games, remaining


def load_cache():
    """Load the odds cache file."""
    if not os.path.exists(CACHE_FILE):
        return {'games': {}, 'last_updated': None, 'requests_remaining': None}
    try:
        with open(CACHE_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, Exception):
        return {'games': {}, 'last_updated': None, 'requests_remaining': None}


def save_cache(cache):
    """Save the odds cache file."""
    with open(CACHE_FILE, 'w') as f:
        json.dump(cache, f, indent=2)


def update_cache(games, remaining):
    """
    Merge freshly fetched odds into the cache.
    Each game is keyed by "AWAY @ HOME" for easy lookup from bet tracker.
    Newer odds overwrite older ones (closer to tip-off = closer to closing line).
    """
    cache = load_cache()
    now = datetime.now(timezone.utc).isoformat()

    for game in games:
        key = f"{game['away_nickname']} @ {game['home_nickname']}"
        cache['games'][key] = {
            'id': game['id'],
            'home': game['home_nickname'],
            'away': game['away_nickname'],
            'home_full': game['home_team'],
            'away_full': game['away_team'],
            'consensus_line': game['consensus_line'],
            'spreads': game['spreads'],
            'commence_time': game['commence_time'],
            'fetched_at': now,
        }

    cache['last_updated'] = now
    cache['requests_remaining'] = remaining
    save_cache(cache)
    return cache


def get_closing_line(away_nickname, home_nickname):
    """
    Look up the cached closing line for a matchup.
    Returns the consensus spread (from home team perspective) or None.
    Accepts either nicknames ("Cavaliers") or full names ("Cleveland Cavaliers").
    """
    cache = load_cache()
    # Try exact key
    key = f"{away_nickname} @ {home_nickname}"
    entry = cache.get('games', {}).get(key)
    if entry:
        return entry.get('consensus_line')

    away_lower = away_nickname.lower()
    home_lower = home_nickname.lower()

    for k, v in cache.get('games', {}).items():
        # Match against nicknames
        if (v.get('away', '').lower() == away_lower and
                v.get('home', '').lower() == home_lower):
            return v.get('consensus_line')
        # Match against full team names
        if (v.get('away_full', '').lower() == away_lower and
                v.get('home_full', '').lower() == home_lower):
            return v.get('consensus_line')

    return None


def print_status():
    """Print cache status and API quota info."""
    cache = load_cache()
    print("\n" + "=" * 60)
    print("  📊 Odds Cache Status")
    print("=" * 60)
    print(f"  Last Updated:      {cache.get('last_updated', 'Never')}")
    print(f"  API Requests Left: {cache.get('requests_remaining', 'Unknown')}")
    print(f"  Cached Games:      {len(cache.get('games', {}))}")

    games = cache.get('games', {})
    if games:
        print(f"\n  {'Matchup':<35} {'Consensus':<12} {'Books':<6} {'Fetched'}")
        print(f"  {'─'*35} {'─'*12} {'─'*6} {'─'*20}")
        for key, g in sorted(games.items()):
            consensus = g.get('consensus_line')
            n_books = len(g.get('spreads', {}))
            fetched = g.get('fetched_at', '?')[:19]
            line_str = f"{consensus:+.1f}" if consensus is not None else "N/A"
            print(f"  {key:<35} {line_str:<12} {n_books:<6} {fetched}")
    print()


def main():
    import sys
    if '--status' in sys.argv:
        print_status()
        return

    print("\n" + "=" * 60)
    print("  🎰 Fetching NBA Odds from The Odds API")
    print("=" * 60)

    games, remaining = fetch_odds()

    if games is None:
        return

    if not games:
        print(f"\n  API Requests Remaining: {remaining}")
        return

    cache = update_cache(games, remaining)

    print(f"\n  ✅ Fetched {len(games)} game(s)")
    print(f"  💾 Cached to {os.path.basename(CACHE_FILE)}")
    print(f"  📡 API Requests Remaining: {remaining}\n")

    print(f"  {'Matchup':<35} {'Consensus':<12} {'Books'}")
    print(f"  {'─'*35} {'─'*12} {'─'*6}")
    for game in games:
        consensus = game['consensus_line']
        n_books = len(game['spreads'])
        line_str = f"{consensus:+.1f}" if consensus is not None else "N/A"
        matchup = f"{game['away_nickname']} @ {game['home_nickname']}"
        print(f"  {matchup:<35} {line_str:<12} {n_books}")

    print()


if __name__ == "__main__":
    main()
