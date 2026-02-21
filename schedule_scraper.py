"""
NBA Schedule Comparison Scraper
Fetches today's NBA schedule from 2 sources and compares them:
  1. ESPN  - HTML scrape of espn.com/nba/schedule
  2. NBA.com - JSON API via CDN (stats.nba.com/stats/scoreboardv3)

Usage:
  python schedule_scraper.py                  # Today's schedule
  python schedule_scraper.py 2026-02-20       # Specific date (YYYY-MM-DD)
"""

import sys
import json
import re
import requests
from datetime import datetime, date
from bs4 import BeautifulSoup

# ── Team Name Normalization ──────────────────────────────────────────────
# Map various team short names / abbreviations to canonical full names
ABBREV_TO_FULL = {
    'ATL': 'Atlanta Hawks',    'BOS': 'Boston Celtics',    'BKN': 'Brooklyn Nets',
    'CHA': 'Charlotte Hornets','CHI': 'Chicago Bulls',     'CLE': 'Cleveland Cavaliers',
    'DAL': 'Dallas Mavericks', 'DEN': 'Denver Nuggets',    'DET': 'Detroit Pistons',
    'GSW': 'Golden State Warriors', 'GS': 'Golden State Warriors',
    'HOU': 'Houston Rockets',  'IND': 'Indiana Pacers',
    'LAC': 'Los Angeles Clippers', 'LAL': 'Los Angeles Lakers',
    'MEM': 'Memphis Grizzlies','MIA': 'Miami Heat',        'MIL': 'Milwaukee Bucks',
    'MIN': 'Minnesota Timberwolves', 'NOP': 'New Orleans Pelicans',
    'NO': 'New Orleans Pelicans',
    'NYK': 'New York Knicks',  'NY': 'New York Knicks',
    'OKC': 'Oklahoma City Thunder', 'ORL': 'Orlando Magic',
    'PHI': 'Philadelphia 76ers','PHX': 'Phoenix Suns',     'PHO': 'Phoenix Suns',
    'POR': 'Portland Trail Blazers',
    'SAC': 'Sacramento Kings',  'SAS': 'San Antonio Spurs', 'SA': 'San Antonio Spurs',
    'TOR': 'Toronto Raptors',   'UTA': 'Utah Jazz',         'WAS': 'Washington Wizards',
    'WSH': 'Washington Wizards',
}

# ESPN uses city names in schedule tables
CITY_TO_FULL = {
    'Atlanta': 'Atlanta Hawks',        'Boston': 'Boston Celtics',
    'Brooklyn': 'Brooklyn Nets',       'Charlotte': 'Charlotte Hornets',
    'Chicago': 'Chicago Bulls',        'Cleveland': 'Cleveland Cavaliers',
    'Dallas': 'Dallas Mavericks',      'Denver': 'Denver Nuggets',
    'Detroit': 'Detroit Pistons',      'Golden State': 'Golden State Warriors',
    'Houston': 'Houston Rockets',      'Indiana': 'Indiana Pacers',
    'LA Clippers': 'Los Angeles Clippers', 'LA Lakers': 'Los Angeles Lakers',
    'Los Angeles Clippers': 'Los Angeles Clippers', 'Los Angeles Lakers': 'Los Angeles Lakers',
    'LA': 'Los Angeles Clippers',              # ESPN in-progress short form
    'Los Angeles': 'Los Angeles Lakers',         # ESPN in-progress short form
    'Memphis': 'Memphis Grizzlies',    'Miami': 'Miami Heat',
    'Milwaukee': 'Milwaukee Bucks',    'Minnesota': 'Minnesota Timberwolves',
    'New Orleans': 'New Orleans Pelicans', 'New York': 'New York Knicks',
    'Oklahoma City': 'Oklahoma City Thunder', 'Orlando': 'Orlando Magic',
    'Philadelphia': 'Philadelphia 76ers', 'Phoenix': 'Phoenix Suns',
    'Portland': 'Portland Trail Blazers',
    'Sacramento': 'Sacramento Kings',  'San Antonio': 'San Antonio Spurs',
    'Toronto': 'Toronto Raptors',      'Utah': 'Utah Jazz',
    'Washington': 'Washington Wizards',
}

NBA_TEAM_NAMES = {
    'Hawks': 'Atlanta Hawks',       'Celtics': 'Boston Celtics',
    'Nets': 'Brooklyn Nets',        'Hornets': 'Charlotte Hornets',
    'Bulls': 'Chicago Bulls',       'Cavaliers': 'Cleveland Cavaliers',
    'Mavericks': 'Dallas Mavericks','Nuggets': 'Denver Nuggets',
    'Pistons': 'Detroit Pistons',   'Warriors': 'Golden State Warriors',
    'Rockets': 'Houston Rockets',   'Pacers': 'Indiana Pacers',
    'Clippers': 'Los Angeles Clippers', 'Lakers': 'Los Angeles Lakers',
    'Grizzlies': 'Memphis Grizzlies','Heat': 'Miami Heat',
    'Bucks': 'Milwaukee Bucks',     'Timberwolves': 'Minnesota Timberwolves',
    'Pelicans': 'New Orleans Pelicans','Knicks': 'New York Knicks',
    'Thunder': 'Oklahoma City Thunder','Magic': 'Orlando Magic',
    '76ers': 'Philadelphia 76ers',  'Suns': 'Phoenix Suns',
    'Trail Blazers': 'Portland Trail Blazers',
    'Kings': 'Sacramento Kings',    'Spurs': 'San Antonio Spurs',
    'Raptors': 'Toronto Raptors',   'Jazz': 'Utah Jazz',
    'Wizards': 'Washington Wizards',
}

def normalize_team(name):
    """Normalize any team name format to canonical full name."""
    name = name.strip()
    # Direct lookups
    if name in ABBREV_TO_FULL:
        return ABBREV_TO_FULL[name]
    if name in CITY_TO_FULL:
        return CITY_TO_FULL[name]
    if name in NBA_TEAM_NAMES:
        return NBA_TEAM_NAMES[name]
    # Handle special case: "LA Clippers" -> "Los Angeles Clippers"
    if name == 'LA Clippers':
        return 'Los Angeles Clippers'
    # Check if it's already a full name
    all_full = set(ABBREV_TO_FULL.values()) | set(CITY_TO_FULL.values())
    if name in all_full:
        return name
    # Fuzzy: check if any full name contains this string
    for full in sorted(all_full):
        if name.lower() == full.lower():
            return full
    return name  # Return as-is if no match


def make_matchup_key(away, home):
    """Create a normalized matchup key for comparison."""
    return (normalize_team(away), normalize_team(home))


# ── Source 1: ESPN Schedule Scraper ──────────────────────────────────────

def scrape_espn(target_date):
    """
    Scrape ESPN NBA schedule for a specific date.
    Uses the ESPN schedule page with date parameter.
    Returns list of dicts: [{away, home, time, line}, ...]
    """
    date_str = target_date.strftime('%Y%m%d')
    url = f"https://www.espn.com/nba/schedule/_/date/{date_str}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) '
                       'Chrome/120.0.0.0 Safari/537.36'
    }

    games = []
    # Build a target date header pattern, e.g. "Thursday, February 19, 2026"
    target_header = target_date.strftime('%A, %B %-d, %Y')

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        text = resp.text

        # ── Strategy: extract the JSON embedded in ESPN's __NEXT_DATA__ ──
        # ESPN embeds full schedule data as JSON in a <script> tag
        json_match = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                games = _parse_espn_next_data(data, target_date)
                if games:
                    return games
            except (json.JSONDecodeError, KeyError):
                pass  # Fall through to HTML parsing

        # ── Fallback: parse the rendered HTML text ──
        # ESPN schedule renders as multi-line blocks:
        #   "Away"  /  "@"  /  "Home"  /  "7:00 PM"  /  ...
        soup = BeautifulSoup(text, 'html.parser')
        full_text = soup.get_text('\n')
        lines = [l.strip() for l in full_text.split('\n')]

        # Find the section for our target date by locating the date header
        target_patterns = [
            target_header.lower(),
            target_date.strftime('%B %-d, %Y').lower(),
            target_date.strftime('%A, %B %d, %Y').lower(),
        ]

        # Locate the start and end indices for our date section
        start_idx = None
        end_idx = len(lines)

        for i, line in enumerate(lines):
            line_lower = line.lower()
            is_target = any(pat in line_lower for pat in target_patterns)
            is_any_date = bool(re.match(
                r'(monday|tuesday|wednesday|thursday|friday|saturday|sunday),\s+\w+\s+\d{1,2},\s+\d{4}',
                line_lower
            ))

            if is_target and start_idx is None:
                start_idx = i + 1
            elif is_any_date and start_idx is not None:
                end_idx = i
                break

        if start_idx is None:
            return games

        # Parse multi-line game blocks within the date section
        # Format: CityName / "@" / CityName / "H:MM PM" / ...
        section = lines[start_idx:end_idx]
        i = 0
        while i < len(section):
            if section[i] == '@':
                away_name = ''
                home_name = ''
                time_str = ''
                line_text = ''

                # Look backward for away team name (skip blanks)
                j = i - 1
                while j >= 0 and not section[j]:
                    j -= 1
                if j >= 0:
                    away_name = section[j]

                # Look forward for home team, then time, then optional odds
                k = i + 1
                while k < len(section) and not section[k]:
                    k += 1
                if k < len(section):
                    home_name = section[k]
                    k += 1

                # Next non-blank should be time
                while k < len(section) and not section[k]:
                    k += 1
                if k < len(section):
                    time_match = re.match(r'\d{1,2}:\d{2}\s*(?:AM|PM)', section[k], re.IGNORECASE)
                    if time_match:
                        time_str = section[k]
                        k += 1

                # Check for betting line in the next few lines
                for look_ahead in range(k, min(k + 4, len(section))):
                    if section[look_ahead].startswith('Line:'):
                        line_text = section[look_ahead]
                        if look_ahead + 1 < len(section) and section[look_ahead + 1].startswith('O/U:'):
                            line_text += ' | ' + section[look_ahead + 1]
                        break

                if away_name and home_name:
                    away_n = normalize_team(away_name)
                    home_n = normalize_team(home_name)
                    if away_n != home_n:
                        key = (away_n, home_n)
                        if not any((g['away'], g['home']) == key for g in games):
                            games.append({
                                'away': away_n,
                                'home': home_n,
                                'time': time_str,
                                'extra': line_text,
                            })
            i += 1

    except Exception as e:
        print(f"  [ESPN ERROR] {e}")

    return games


def _parse_espn_next_data(data, target_date):
    """Parse ESPN's __NEXT_DATA__ JSON for schedule entries on target_date."""
    games = []
    target_str = target_date.strftime('%Y%m%d')  # e.g. "20260219"
    target_iso = target_date.isoformat()  # e.g. "2026-02-19"

    # Navigate the nested JSON structure — ESPN changes this periodically
    # Try common paths
    def find_events(obj, depth=0):
        """Recursively search for game/event arrays in ESPN JSON."""
        if depth > 10:
            return []
        found = []
        if isinstance(obj, dict):
            # Check if this dict looks like a game event
            if 'competitions' in obj or ('shortName' in obj and 'date' in obj):
                found.append(obj)
            for v in obj.values():
                found.extend(find_events(v, depth + 1))
        elif isinstance(obj, list):
            for item in obj:
                found.extend(find_events(item, depth + 1))
        return found

    events = find_events(data)

    for event in events:
        # Check date matches
        event_date = event.get('date', '')
        if not (target_str in event_date or target_iso in event_date):
            # Try extracting date from the event date string
            if event_date:
                try:
                    evt_dt = datetime.fromisoformat(event_date.replace('Z', '+00:00'))
                    if evt_dt.date() != target_date:
                        continue
                except (ValueError, TypeError):
                    continue
            else:
                continue

        competitions = event.get('competitions', [event])
        for comp in competitions:
            competitors = comp.get('competitors', [])
            away_team = home_team = None
            for c in competitors:
                home_away = c.get('homeAway', '')
                team_info = c.get('team', {})
                name = (team_info.get('displayName') or
                        team_info.get('shortDisplayName') or
                        team_info.get('abbreviation', ''))
                resolved = normalize_team(name)
                # If primary fields didn't resolve, try abbreviation (always unambiguous)
                if resolved == name and team_info.get('abbreviation'):
                    fallback = normalize_team(team_info['abbreviation'])
                    if fallback != team_info['abbreviation']:
                        resolved = fallback
                if home_away == 'away':
                    away_team = resolved
                elif home_away == 'home':
                    home_team = resolved

            if away_team and home_team:
                time_str = event.get('status', {}).get('type', {}).get('shortDetail', '')
                key = (away_team, home_team)
                if not any((g['away'], g['home']) == key for g in games):
                    games.append({
                        'away': away_team,
                        'home': home_team,
                        'time': time_str,
                        'extra': '',
                    })

    return games


# ── Source 2: NBA.com CDN/API ────────────────────────────────────────────

def scrape_nba_com(target_date):
    """
    Fetch NBA schedule from NBA.com's stats API (scoreboardv3).
    This is a JSON API that doesn't require Selenium.
    Returns list of dicts: [{away, home, time, game_id}, ...]
    """
    date_str = target_date.strftime('%Y-%m-%d')
    url = f"https://stats.nba.com/stats/scoreboardv3?GameDate={date_str}&LeagueID=00"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) '
                       'Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.nba.com/',
        'Origin': 'https://www.nba.com',
        'Accept': 'application/json',
        'x-nba-stats-origin': 'stats',
        'x-nba-stats-token': 'true',
    }

    games = []
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        scoreboard = data.get('scoreboard', {})
        for game in scoreboard.get('games', []):
            away_team = game.get('awayTeam', {})
            home_team = game.get('homeTeam', {})

            away_name = away_team.get('teamName', '')
            home_name = home_team.get('teamName', '')
            away_city = away_team.get('teamCity', '')
            home_city = home_team.get('teamCity', '')
            away_tricode = away_team.get('teamTricode', '')
            home_tricode = home_team.get('teamTricode', '')
            game_id = game.get('gameId', '')
            game_time = game.get('gameTimeUTC', '')
            game_status = game.get('gameStatusText', '')

            games.append({
                'away': normalize_team(away_tricode) if away_tricode else f"{away_city} {away_name}",
                'home': normalize_team(home_tricode) if home_tricode else f"{home_city} {home_name}",
                'time': game_status or game_time,
                'game_id': game_id,
                'away_tricode': away_tricode,
                'home_tricode': home_tricode,
            })

    except Exception as e:
        print(f"  [NBA.com API ERROR] {e}")

    # Fallback: try the CDN endpoint
    if not games:
        try:
            cdn_url = f"https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json"
            resp = requests.get(cdn_url, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            scoreboard = data.get('scoreboard', {})
            for game in scoreboard.get('games', []):
                away_team = game.get('awayTeam', {})
                home_team = game.get('homeTeam', {})
                games.append({
                    'away': normalize_team(away_team.get('teamTricode', away_team.get('teamName', ''))),
                    'home': normalize_team(home_team.get('teamTricode', home_team.get('teamName', ''))),
                    'time': game.get('gameStatusText', ''),
                    'game_id': game.get('gameId', ''),
                    'away_tricode': away_team.get('teamTricode', ''),
                    'home_tricode': home_team.get('teamTricode', ''),
                })
            if games:
                print(f"  [NBA.com] scoreboardv3 failed, used CDN fallback ({len(games)} games)")
        except Exception as e2:
            print(f"  [NBA.com CDN ERROR] {e2}")

    return games


# ── Comparison Logic ─────────────────────────────────────────────────────

def compare_sources(espn, nba_com, target_date):
    """Compare game lists from ESPN and NBA.com and print a detailed report."""

    def to_matchup_set(games):
        return {make_matchup_key(g['away'], g['home']) for g in games}

    espn_set = to_matchup_set(espn)
    nba_com_set = to_matchup_set(nba_com)

    # Union of all games
    all_matchups = sorted(espn_set | nba_com_set)

    date_display = target_date.strftime('%A, %B %d, %Y')

    print("\n" + "=" * 70)
    print(f"  NBA SCHEDULE COMPARISON — {date_display}")
    print("=" * 70)

    # Summary counts
    print(f"\n{'Source':<30} {'Games Found':>12}")
    print("-" * 42)
    print(f"{'ESPN (web scrape)':<30} {len(espn):>12}")
    print(f"{'NBA.com (scoreboardv3 API)':<30} {len(nba_com):>12}")

    if not all_matchups:
        print("\n  No games found from any source.")
        return

    # Detailed comparison table
    print(f"\n{'#':<4} {'Away':<26} {'Home':<26} {'ESPN':^6} {'NBA':^6}")
    print("-" * 70)

    for i, (away, home) in enumerate(all_matchups, 1):
        in_espn = '✓' if (away, home) in espn_set else '✗'
        in_nba = '✓' if (away, home) in nba_com_set else '✗'

        # Find time from the best available source
        time_str = ''
        for src in [espn, nba_com]:
            for g in src:
                if make_matchup_key(g['away'], g['home']) == (away, home):
                    time_str = g.get('time', '')
                    break
            if time_str:
                break

        print(f"{i:<4} {away:<26} {home:<26} {in_espn:^6} {in_nba:^6}   {time_str}")

    # Discrepancy analysis
    print("\n" + "-" * 70)
    print("DISCREPANCY ANALYSIS:")
    print("-" * 70)

    has_discrepancy = False

    # Games missing from ESPN
    missing_espn = nba_com_set - espn_set
    if missing_espn:
        has_discrepancy = True
        print(f"\n  ⚠  ESPN is MISSING {len(missing_espn)} game(s):")
        for away, home in sorted(missing_espn):
            print(f"     • {away} @ {home}")

    # Games missing from NBA.com
    missing_nba = espn_set - nba_com_set
    if missing_nba:
        has_discrepancy = True
        print(f"\n  ⚠  NBA.com API is MISSING {len(missing_nba)} game(s):")
        for away, home in sorted(missing_nba):
            print(f"     • {away} @ {home}")

    in_all = espn_set & nba_com_set

    if not has_discrepancy:
        print("\n  ✅ Both sources agree on the schedule!")
    elif in_all:
        print(f"\n  ✅ {len(in_all)} game(s) confirmed across both sources.")

    print("\n" + "=" * 70)


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    # Parse optional date argument
    if len(sys.argv) > 1:
        try:
            target_date = datetime.strptime(sys.argv[1], '%Y-%m-%d').date()
        except ValueError:
            print(f"Invalid date format: {sys.argv[1]}. Use YYYY-MM-DD.")
            sys.exit(1)
    else:
        target_date = date.today()

    print(f"\n🏀 NBA Schedule Comparison — {target_date.strftime('%A, %B %d, %Y')}")
    print("=" * 60)

    # Fetch from both sources
    print("\n[1/2] Scraping ESPN schedule...")
    espn = scrape_espn(target_date)
    print(f"       → {len(espn)} games found")

    print("[2/2] Fetching NBA.com scoreboardv3 API...")
    nba_com = scrape_nba_com(target_date)
    print(f"       → {len(nba_com)} games found")

    # Compare
    compare_sources(espn, nba_com, target_date)


if __name__ == '__main__':
    main()
