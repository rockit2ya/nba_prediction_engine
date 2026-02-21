#!/usr/bin/env python3
"""
preflight_check.py — Pre-Bet Validation & Data Health Monitor
=============================================================

Run this BEFORE placing any bets each game day.
It audits every data feed, model factor, and downstream calculation
to catch silent failures, stale data, or out-of-range values.

Usage:
    python preflight_check.py              # Full audit (stamps tracker on pass)
    python preflight_check.py --quick      # Data freshness + structure only
    python preflight_check.py --fix        # Re-run scrapers for any FAIL items
    python preflight_check.py --backfill   # Add PreflightCheck/Note columns to all historical trackers
"""

import os
import sys
import json
import csv
import math
import glob
import subprocess
from datetime import datetime, timedelta
from io import StringIO
from collections import Counter

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

# Expected 30 NBA teams (canonical full names)
EXPECTED_TEAMS = {
    'Atlanta Hawks', 'Boston Celtics', 'Brooklyn Nets', 'Charlotte Hornets',
    'Chicago Bulls', 'Cleveland Cavaliers', 'Dallas Mavericks', 'Denver Nuggets',
    'Detroit Pistons', 'Golden State Warriors', 'Houston Rockets', 'Indiana Pacers',
    'Los Angeles Clippers', 'Los Angeles Lakers', 'Memphis Grizzlies', 'Miami Heat',
    'Milwaukee Bucks', 'Minnesota Timberwolves', 'New Orleans Pelicans',
    'New York Knicks', 'Oklahoma City Thunder', 'Orlando Magic',
    'Philadelphia 76ers', 'Phoenix Suns', 'Portland Trail Blazers',
    'Sacramento Kings', 'San Antonio Spurs', 'Toronto Raptors', 'Utah Jazz',
    'Washington Wizards',
}

# Valid injury statuses the model recognises (lowercase substrings)
KNOWN_STATUS_KEYWORDS = {
    'out', 'doubtful', 'questionable', 'probable',
    'game time decision', 'day-to-day', 'out for the season',
}

# Reasonable NBA ranges
PACE_RANGE = (92.0, 108.0)
ORTG_RANGE = (100.0, 125.0)
DRTG_RANGE = (100.0, 125.0)
NET_RATING_RANGE = (-20.0, 20.0)
SPREAD_RANGE = (-30.0, 30.0)      # fair line and market line
STAR_TAX_RANGE = (-30.0, 30.0)    # per-player on-off net rating (bench players can be extreme)
REST_PENALTY_RANGE = (-4.0, 4.0)
KELLY_RANGE = (0.0, 15.0)         # quarter-kelly %
EDGE_RANGE = (0.0, 30.0)          # raw edge pts (capped separately)

STALE_HOURS = 18  # data older than this is flagged

# ── Helpers ───────────────────────────────────────────────────────────────────
PASS = 0
WARN = 0
FAIL = 0
FAIL_DETAILS = []   # list of (label, message, fix_hint)
WARN_DETAILS = []   # list of (label, message, fix_hint)

def _ts(label, status, msg, detail=None, fix=None):
    """Print a check result line.
    
    Args:
        fix: Remediation hint shown in the summary when status is FAIL or WARN.
    """
    global PASS, WARN, FAIL
    icons = {'PASS': '✅', 'WARN': '⚠️ ', 'FAIL': '❌'}
    icon = icons.get(status, '  ')
    print(f"  {icon} [{label:.<40s}] {msg}")
    if detail:
        for d in (detail if isinstance(detail, list) else [detail]):
            print(f"       ↳ {d}")
    if status == 'PASS':
        PASS += 1
    elif status == 'WARN':
        WARN += 1
        if fix:
            WARN_DETAILS.append((label, msg, fix))
    elif status == 'FAIL':
        FAIL += 1
        FAIL_DETAILS.append((label, msg, fix or 'No auto-fix available — investigate manually.'))

def _parse_ts(raw):
    """Try to parse a timestamp string into datetime."""
    if not raw or raw in ('Unknown', 'Missing'):
        return None
    for fmt in (
        '%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f',
    ):
        try:
            return datetime.strptime(raw.strip(), fmt)
        except ValueError:
            continue
    return None

def _freshness(ts_dt, label):
    """Check if a timestamp is recent enough."""
    if ts_dt is None:
        _ts(label, 'FAIL', 'Timestamp missing or unparseable',
            fix='Re-run: bash fetch_all_nba_data.sh')
        return
    age = datetime.now() - ts_dt
    hrs = age.total_seconds() / 3600
    if hrs > STALE_HOURS:
        _ts(label, 'WARN', f'Data is {hrs:.1f}h old (stale > {STALE_HOURS}h)',
            f'Last updated: {ts_dt.strftime("%Y-%m-%d %H:%M:%S")}',
            fix='Re-run: bash fetch_all_nba_data.sh  (refreshes all data feeds)')
    else:
        _ts(label, 'PASS', f'Fresh ({hrs:.1f}h old)')

def _in_range(val, lo, hi, label, unit=''):
    """Check a numeric value is in expected range."""
    try:
        v = float(val)
    except (ValueError, TypeError):
        _ts(label, 'FAIL', f'Non-numeric value: {val!r}')
        return False
    if v < lo or v > hi:
        _ts(label, 'WARN', f'{v}{unit} outside expected [{lo}, {hi}]')
        return False
    return True


# ══════════════════════════════════════════════════════════════════════════════
#  Section 1: DATA FEED CHECKS
# ══════════════════════════════════════════════════════════════════════════════
def check_stats_cache():
    """Validate nba_stats_cache.json — team ratings from NBA.com."""
    print("\n─── 1. TEAM STATS (nba_stats_cache.json) ─────────────────────────")
    path = 'nba_stats_cache.json'
    if not os.path.exists(path):
        _ts('stats.exists', 'FAIL', 'File not found',
            fix='Run: bash fetch_all_nba_data.sh stats')
        return {}

    try:
        with open(path) as f:
            cache = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        _ts('stats.parse', 'FAIL', f'JSON parse error: {e}',
            fix='Delete nba_stats_cache.json and re-run: bash fetch_all_nba_data.sh stats')
        return {}

    _ts('stats.parse', 'PASS', 'JSON valid')

    # Timestamp
    ts = _parse_ts(cache.get('timestamp', ''))
    _freshness(ts, 'stats.freshness')

    # Data structure
    data = cache.get('data')
    if not data or not isinstance(data, dict):
        _ts('stats.structure', 'FAIL', 'Missing or invalid "data" key',
            fix='Delete nba_stats_cache.json and re-run: bash fetch_all_nba_data.sh stats')
        return {}

    # TEAM_ID is added programmatically by calculate_pace_and_ratings() — not in raw cache
    required_cols = ['TEAM_NAME', 'PACE', 'OFF_RATING', 'DEF_RATING', 'NET_RATING']
    missing_cols = [c for c in required_cols if c not in data]
    if missing_cols:
        _ts('stats.columns', 'FAIL', f'Missing columns: {missing_cols}',
            fix='NBA.com API may have changed format. Delete nba_stats_cache.json and re-run: bash fetch_all_nba_data.sh stats')
        return {}
    _ts('stats.columns', 'PASS', f'All {len(required_cols)} required columns present')

    # TEAM_ID is optional in raw cache (added by code from TEAM_NAME_TO_ID)
    if 'TEAM_ID' not in data:
        _ts('stats.team_id_col', 'PASS', 'TEAM_ID not in raw cache (added programmatically — OK)')
    else:
        _ts('stats.team_id_col', 'PASS', 'TEAM_ID present in raw cache')

    # Team count (normalize "LA Clippers" same as calculate_pace_and_ratings does)
    teams = list(data['TEAM_NAME'].values())
    team_set = set('Los Angeles Clippers' if t == 'LA Clippers' else t for t in teams)
    raw_team_set = set(teams)  # before normalization
    if len(team_set) == 30:
        _ts('stats.team_count', 'PASS', '30 teams present')
    else:
        _ts('stats.team_count', 'FAIL', f'{len(team_set)} teams (expected 30)',
            f'Missing: {EXPECTED_TEAMS - team_set}' if team_set < EXPECTED_TEAMS else None,
            fix='Re-run: bash fetch_all_nba_data.sh stats')

    # Check for "LA Clippers" vs "Los Angeles Clippers" in raw data
    if 'LA Clippers' in raw_team_set:
        _ts('stats.clippers_name', 'WARN', '"LA Clippers" in raw cache — normalised at load time by code')
    elif 'Los Angeles Clippers' in raw_team_set:
        _ts('stats.clippers_name', 'PASS', 'Clippers canonical name correct')

    # Cross-check team names vs canonical (use normalized set)
    unknowns = team_set - EXPECTED_TEAMS
    if unknowns:
        _ts('stats.unknown_teams', 'WARN', f'Unexpected team names: {unknowns}')

    # Value ranges
    idx_keys = list(data['TEAM_NAME'].keys())
    range_ok = True
    outliers = []
    for idx in idx_keys:
        tn = data['TEAM_NAME'][idx]
        pace = float(data['PACE'][idx])
        ortg = float(data['OFF_RATING'][idx])
        drtg = float(data['DEF_RATING'][idx])
        net = float(data['NET_RATING'][idx])
        if not (PACE_RANGE[0] <= pace <= PACE_RANGE[1]):
            outliers.append(f'{tn}: PACE={pace}')
            range_ok = False
        if not (ORTG_RANGE[0] <= ortg <= ORTG_RANGE[1]):
            outliers.append(f'{tn}: ORtg={ortg}')
            range_ok = False
        if not (DRTG_RANGE[0] <= drtg <= DRTG_RANGE[1]):
            outliers.append(f'{tn}: DRtg={drtg}')
            range_ok = False
        if not (NET_RATING_RANGE[0] <= net <= NET_RATING_RANGE[1]):
            outliers.append(f'{tn}: NET={net}')
            range_ok = False
    if range_ok:
        _ts('stats.value_ranges', 'PASS', 'All PACE/ORtg/DRtg/NET in expected ranges')
    else:
        _ts('stats.value_ranges', 'WARN', f'{len(outliers)} outlier(s)',
            outliers[:5] + (['...'] if len(outliers) > 5 else []))

    return {'teams': team_set, 'data': data, 'timestamp': ts}


def check_injuries_cache():
    """Validate nba_injuries.csv — CBS Sports injury data."""
    print("\n─── 2. INJURIES (nba_injuries.csv) ───────────────────────────────")
    path = 'nba_injuries.csv'
    if not os.path.exists(path):
        _ts('injuries.exists', 'FAIL', 'File not found',
            fix='Run: bash fetch_all_nba_data.sh injuries')
        return {}

    with open(path) as f:
        lines = f.readlines()
    if not lines:
        _ts('injuries.empty', 'FAIL', 'File is empty',
            fix='Run: bash fetch_all_nba_data.sh injuries')
        return {}

    # Timestamp
    ts = None
    csv_lines = lines
    if lines[0].startswith('# timestamp:'):
        ts_raw = lines[0].strip().split(':', 1)[1].strip()
        ts = _parse_ts(ts_raw)
        csv_lines = lines[1:]
    _freshness(ts, 'injuries.freshness')

    # Parse CSV
    try:
        reader = csv.DictReader(csv_lines)
        rows = list(reader)
    except Exception as e:
        _ts('injuries.parse', 'FAIL', f'CSV parse error: {e}',
            fix='Delete nba_injuries.csv and re-run: bash fetch_all_nba_data.sh injuries')
        return {}

    if not rows:
        _ts('injuries.empty', 'WARN', 'No injury rows — is this correct? (healthy league?)')
        return {'rows': rows}

    _ts('injuries.parse', 'PASS', f'{len(rows)} injury records loaded')

    # Required columns
    required = ['team', 'player', 'status']
    cols = list(rows[0].keys())
    missing = [c for c in required if c not in cols]
    if missing:
        _ts('injuries.columns', 'FAIL', f'Missing columns: {missing}', f'Found: {cols}',
            fix='CBS Sports format may have changed. Check injury_scraper.py for updates.')
    else:
        _ts('injuries.columns', 'PASS', f'Required columns present: {required}')

    # Team coverage
    teams = set(r['team'] for r in rows)
    _ts('injuries.team_count', 'PASS' if len(teams) >= 20 else 'WARN',
        f'{len(teams)} teams have injuries')

    # Team names match canonical
    bad_teams = teams - EXPECTED_TEAMS
    if bad_teams:
        _ts('injuries.team_names', 'FAIL', f'Unknown team names: {bad_teams}',
            'These won\'t match model lookups — check injury_scraper.py CBS_TEAM_MAP',
            fix='Add the missing team name(s) to CBS_TEAM_MAP in injury_scraper.py, then re-run: bash fetch_all_nba_data.sh injuries')
    else:
        _ts('injuries.team_names', 'PASS', 'All team names are canonical')

    # Player names not empty/garbled
    empty_names = [r for r in rows if not r['player'] or len(r['player']) < 3]
    if empty_names:
        _ts('injuries.player_names', 'FAIL', f'{len(empty_names)} player(s) with empty/short names',
            [f"{r['team']}: {r['player']!r}" for r in empty_names[:3]],
            fix='CBS Sports HTML structure may have changed. Check injury_scraper.py CSS selectors.')
    else:
        _ts('injuries.player_names', 'PASS', 'All player names look valid')

    # Concatenated names check (old bug: "JohnSmithJaneDoe")
    concat_suspects = [r for r in rows if r['player'] and len(r['player']) > 30 and ' ' not in r['player']]
    if concat_suspects:
        _ts('injuries.concat_names', 'FAIL', f'{len(concat_suspects)} possibly concatenated name(s)',
            [f"{r['team']}: {r['player']}" for r in concat_suspects[:3]],
            fix='Player name parsing broken — check injury_scraper.py (CellPlayerName--long selector).')

    # Status recognition
    unrecognised = []
    for r in rows:
        s = r.get('status', '').lower()
        if not any(kw in s for kw in KNOWN_STATUS_KEYWORDS):
            unrecognised.append(f"{r['player']}: {r['status']!r}")
    if unrecognised:
        _ts('injuries.status_values', 'WARN',
            f'{len(unrecognised)} status(es) not matching known keywords',
            unrecognised[:5] + (['...'] if len(unrecognised) > 5 else []))
    else:
        _ts('injuries.status_values', 'PASS', 'All statuses contain recognised keywords')

    return {'rows': rows, 'teams': teams, 'timestamp': ts}


def check_star_tax_cache():
    """Validate nba_star_tax_cache.json — On/Off player impact data."""
    print("\n─── 3. STAR TAX (nba_star_tax_cache.json) ────────────────────────")
    path = 'nba_star_tax_cache.json'
    if not os.path.exists(path):
        _ts('star_tax.exists', 'FAIL', 'File not found',
            fix='Run: bash fetch_all_nba_data.sh star_tax')
        return {}

    try:
        with open(path) as f:
            cache = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        _ts('star_tax.parse', 'FAIL', f'JSON parse error: {e}',
            fix='Delete nba_star_tax_cache.json and re-run: bash fetch_all_nba_data.sh star_tax')
        return {}

    _ts('star_tax.parse', 'PASS', 'JSON valid')

    ts = _parse_ts(cache.get('timestamp', ''))
    _freshness(ts, 'star_tax.freshness')

    teams = cache.get('teams', {})
    if not teams:
        _ts('star_tax.structure', 'FAIL', 'No "teams" key or empty',
            fix='Delete nba_star_tax_cache.json and re-run: bash fetch_all_nba_data.sh star_tax')
        return {}

    if len(teams) == 30:
        _ts('star_tax.team_count', 'PASS', '30 teams in cache')
    else:
        _ts('star_tax.team_count', 'FAIL', f'{len(teams)} teams in cache (expected 30)',
            fix='Re-run: bash fetch_all_nba_data.sh star_tax')

    # Check TEAM_ID keys are valid integers
    from nba_teams_static import TEAM_ID_TO_NAME
    bad_ids = []
    teams_with_errors = []
    teams_with_no_players = []
    outlier_players = []
    total_players = 0

    for tid_str, tdata in teams.items():
        try:
            tid_int = int(tid_str)
        except ValueError:
            bad_ids.append(tid_str)
            continue
        if tid_int not in TEAM_ID_TO_NAME:
            bad_ids.append(f'{tid_str} (not a valid NBA team ID)')
        if 'error' in tdata:
            teams_with_errors.append(f'{TEAM_ID_TO_NAME.get(tid_int, tid_str)}: {tdata["error"]}')
        players = tdata.get('players', {})
        if not players and 'error' not in tdata:
            teams_with_no_players.append(TEAM_ID_TO_NAME.get(tid_int, tid_str))
        total_players += len(players)
        for pname, pm in players.items():
            try:
                v = float(pm)
                if not (STAR_TAX_RANGE[0] <= v <= STAR_TAX_RANGE[1]):
                    outlier_players.append(f'{pname}: {v}')
            except (ValueError, TypeError):
                outlier_players.append(f'{pname}: non-numeric {pm!r}')

    if bad_ids:
        _ts('star_tax.team_ids', 'FAIL', f'{len(bad_ids)} invalid team ID(s)', bad_ids[:5],
            fix='Check star_tax_prefetch.py — team IDs should be integers like 1610612737')
    else:
        _ts('star_tax.team_ids', 'PASS', 'All team IDs are valid integers')

    if teams_with_errors:
        _ts('star_tax.fetch_errors', 'WARN', f'{len(teams_with_errors)} team(s) had scrape errors',
            teams_with_errors[:5])
    else:
        _ts('star_tax.fetch_errors', 'PASS', 'No team fetch errors')

    _ts('star_tax.player_count', 'PASS' if total_players >= 300 else 'WARN',
        f'{total_players} total player impact records')

    if teams_with_no_players:
        _ts('star_tax.empty_rosters', 'WARN', f'{len(teams_with_no_players)} team(s) with 0 players',
            teams_with_no_players[:5])

    if outlier_players:
        _ts('star_tax.value_ranges', 'WARN', f'{len(outlier_players)} outlier impact value(s)',
            outlier_players[:5])
    else:
        _ts('star_tax.value_ranges', 'PASS', f'All player impacts within [{STAR_TAX_RANGE[0]}, {STAR_TAX_RANGE[1]}]')

    # Check lookup_by key
    lookup = cache.get('lookup_by', '')
    if lookup == 'player_name':
        _ts('star_tax.lookup_mode', 'PASS', 'Lookup by player_name (Selenium cache)')
    elif lookup:
        _ts('star_tax.lookup_mode', 'WARN', f'Unexpected lookup_by: {lookup!r}')
    else:
        _ts('star_tax.lookup_mode', 'WARN', 'No lookup_by key — will auto-detect')

    return {'teams': teams, 'total_players': total_players, 'timestamp': ts}


def check_rest_penalty_cache():
    """Validate nba_rest_penalty_cache.csv — back-to-back / fatigue data."""
    print("\n─── 4. REST PENALTIES (nba_rest_penalty_cache.csv) ───────────────")
    path = 'nba_rest_penalty_cache.csv'
    if not os.path.exists(path):
        _ts('rest.exists', 'FAIL', 'File not found',
            fix='Run: bash fetch_all_nba_data.sh rest')
        return {}

    with open(path) as f:
        lines = f.readlines()

    ts = None
    csv_lines = lines
    if lines and lines[0].startswith('#'):
        ts_raw = lines[0].strip().split(':', 1)[1].strip()
        ts = _parse_ts(ts_raw)
        csv_lines = lines[1:]
    _freshness(ts, 'rest.freshness')

    try:
        reader = csv.DictReader(csv_lines)
        rows = list(reader)
    except Exception as e:
        _ts('rest.parse', 'FAIL', f'CSV parse error: {e}',
            fix='Delete nba_rest_penalty_cache.csv and re-run: bash fetch_all_nba_data.sh rest')
        return {}

    if not rows:
        _ts('rest.empty', 'FAIL', 'No data rows',
            fix='Run: bash fetch_all_nba_data.sh rest')
        return {}

    _ts('rest.parse', 'PASS', f'{len(rows)} rows')

    # 30 teams
    teams = set(r.get('TEAM_NAME', '') for r in rows)
    if len(teams) == 30:
        _ts('rest.team_count', 'PASS', '30 teams present')
    else:
        _ts('rest.team_count', 'FAIL', f'{len(teams)} teams (expected 30)',
            f'Missing: {EXPECTED_TEAMS - teams}' if teams < EXPECTED_TEAMS else None,
            fix='Re-run: bash fetch_all_nba_data.sh rest')

    # Team names canonical
    bad = teams - EXPECTED_TEAMS
    if bad:
        _ts('rest.team_names', 'FAIL', f'Non-canonical names: {bad}',
            fix='Add missing name(s) to SHORT_TO_FULL_TEAM in rest_penalty_scraper.py, then re-run: bash fetch_all_nba_data.sh rest')
    else:
        _ts('rest.team_names', 'PASS', 'All canonical')

    # Value ranges
    outliers = []
    for r in rows:
        tn = r.get('TEAM_NAME', '?')
        try:
            v = float(r.get('REST_PENALTY', 0))
            if not (REST_PENALTY_RANGE[0] <= v <= REST_PENALTY_RANGE[1]):
                outliers.append(f'{tn}: {v}')
        except ValueError:
            outliers.append(f'{tn}: non-numeric {r.get("REST_PENALTY")!r}')

    if outliers:
        _ts('rest.value_ranges', 'WARN', f'{len(outliers)} outlier(s)', outliers[:5])
    else:
        _ts('rest.value_ranges', 'PASS', f'All penalties within [{REST_PENALTY_RANGE[0]}, {REST_PENALTY_RANGE[1]}]')

    # Check that B2B teams actually show non-zero
    nonzero = [r for r in rows if float(r.get('REST_PENALTY', 0)) != 0.0]
    _ts('rest.b2b_teams', 'PASS' if nonzero else 'WARN',
        f'{len(nonzero)} team(s) have non-zero rest penalty' + (' (none on B2B today?)' if not nonzero else ''))

    return {'rows': rows, 'teams': teams, 'timestamp': ts}


def check_odds_cache():
    """Validate odds_cache.json — The Odds API spread data."""
    print("\n─── 5. ODDS / MARKET LINES (odds_cache.json) ────────────────────")
    path = 'odds_cache.json'
    if not os.path.exists(path):
        _ts('odds.exists', 'FAIL', 'File not found',
            fix='Run: bash fetch_all_nba_data.sh odds')
        return {}

    try:
        with open(path) as f:
            cache = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        _ts('odds.parse', 'FAIL', f'JSON parse error: {e}',
            fix='Delete odds_cache.json and re-run: bash fetch_all_nba_data.sh odds')
        return {}

    _ts('odds.parse', 'PASS', 'JSON valid')

    games = cache.get('games', {})
    if not games:
        _ts('odds.games', 'FAIL', 'No "games" key or empty',
            fix='Run: bash fetch_all_nba_data.sh odds  (check ODDS_API_KEY in .env)')
        return {}

    _ts('odds.game_count', 'PASS', f'{len(games)} games in cache')

    # Check each game entry
    issues = []
    team_names_seen = set()
    for key, g in games.items():
        # Required fields
        for field in ('home', 'away', 'home_full', 'away_full', 'consensus_line', 'spreads'):
            if field not in g:
                issues.append(f'{key}: missing "{field}"')
        # Full names should be canonical
        for role in ('home_full', 'away_full'):
            fn = g.get(role, '')
            team_names_seen.add(fn)
            if fn and fn not in EXPECTED_TEAMS:
                issues.append(f'{key}: {role}={fn!r} not canonical')
        # Consensus line in range
        cl = g.get('consensus_line')
        if cl is not None:
            try:
                v = float(cl)
                if not (SPREAD_RANGE[0] <= v <= SPREAD_RANGE[1]):
                    issues.append(f'{key}: consensus_line={v} out of range')
            except (ValueError, TypeError):
                issues.append(f'{key}: consensus_line non-numeric: {cl!r}')
        # Spreads dict should have at least 1 book
        spreads = g.get('spreads', {})
        if not spreads:
            issues.append(f'{key}: empty spreads dict')
        elif len(spreads) < 2:
            issues.append(f'{key}: only {len(spreads)} book(s) — thin market')
        # Check for huge spread variance (possible stale outlier)
        if spreads:
            spread_vals = [float(v) for v in spreads.values()]
            spread_range = max(spread_vals) - min(spread_vals)
            if spread_range > 8:
                issues.append(f'{key}: spread variance {spread_range} pts — possible stale book')

    if issues:
        _ts('odds.integrity', 'WARN', f'{len(issues)} issue(s)', issues[:8])
    else:
        _ts('odds.integrity', 'PASS', 'All game entries well-formed')

    # Freshness per game (fetched_at is UTC — convert to local)
    latest_fetch = None
    for g in games.values():
        raw_ft = g.get('fetched_at', '')
        # Strip timezone offset for naive comparison
        clean = raw_ft.split('+')[0].split('Z')[0] if raw_ft else ''
        ft = _parse_ts(clean)
        if ft and (latest_fetch is None or ft > latest_fetch):
            latest_fetch = ft
    # Approximate UTC→local adjustment
    if latest_fetch:
        import time as _time
        utc_offset = timedelta(seconds=-_time.timezone if _time.daylight == 0 else -_time.altzone)
        latest_fetch = latest_fetch + utc_offset
    _freshness(latest_fetch, 'odds.freshness')

    return {'games': games, 'team_names': team_names_seen}


def check_schedule_cache():
    """Validate nba_schedule_cache.json — game schedule from ESPN."""
    print("\n─── 6. SCHEDULE (nba_schedule_cache.json) ────────────────────────")
    path = 'nba_schedule_cache.json'
    if not os.path.exists(path):
        _ts('schedule.exists', 'FAIL', 'File not found',
            fix='Run: bash fetch_all_nba_data.sh schedule')
        return {}

    try:
        with open(path) as f:
            cache = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        _ts('schedule.parse', 'FAIL', f'JSON parse error: {e}',
            fix='Delete nba_schedule_cache.json and re-run: bash fetch_all_nba_data.sh schedule')
        return {}

    _ts('schedule.parse', 'PASS', 'JSON valid')
    ts = _parse_ts(cache.get('timestamp', ''))
    _freshness(ts, 'schedule.freshness')

    dates = cache.get('dates', {})
    if not dates:
        _ts('schedule.dates', 'FAIL', 'No "dates" key or empty',
            fix='Run: bash fetch_all_nba_data.sh schedule')
        return {}

    _ts('schedule.dates', 'PASS', f'{len(dates)} date(s) cached')

    # Today's games
    today_str = datetime.now().strftime('%Y-%m-%d')
    today_entry = dates.get(today_str, {})
    today_games = today_entry.get('games', []) if isinstance(today_entry, dict) else []

    if today_games:
        _ts('schedule.today', 'PASS', f'{len(today_games)} game(s) scheduled for today')
        # Check team names
        sched_teams = set()
        for g in today_games:
            sched_teams.add(g.get('away', ''))
            sched_teams.add(g.get('home', ''))
        bad = sched_teams - EXPECTED_TEAMS
        if bad:
            _ts('schedule.team_names', 'WARN', f'Non-canonical names in schedule: {bad}')
        else:
            _ts('schedule.team_names', 'PASS', 'All schedule team names canonical')
    else:
        _ts('schedule.today', 'WARN', 'No games found for today — off day or stale cache?')

    return {'dates': dates, 'today_games': today_games, 'timestamp': ts}


def check_news_cache():
    """Validate nba_news_cache.json — ESPN RSS news feed."""
    print("\n─── 7. NEWS (nba_news_cache.json) ────────────────────────────────")
    path = 'nba_news_cache.json'
    if not os.path.exists(path):
        _ts('news.exists', 'FAIL', 'File not found',
            fix='Run: bash fetch_all_nba_data.sh news')
        return {}

    try:
        with open(path) as f:
            cache = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        _ts('news.parse', 'FAIL', f'JSON parse error: {e}',
            fix='Delete nba_news_cache.json and re-run: bash fetch_all_nba_data.sh news')
        return {}

    _ts('news.parse', 'PASS', 'JSON valid')
    ts = _parse_ts(cache.get('timestamp', ''))
    _freshness(ts, 'news.freshness')

    articles = cache.get('data', [])
    if not articles:
        _ts('news.articles', 'WARN', 'No articles in cache')
        return {}

    _ts('news.article_count', 'PASS', f'{len(articles)} articles')

    # Check article structure
    bad = [a for a in articles if 'title' not in a or 'summary' not in a]
    if bad:
        _ts('news.structure', 'WARN', f'{len(bad)} article(s) missing title/summary')
    else:
        _ts('news.structure', 'PASS', 'All articles have title + summary')

    return {'articles': articles, 'timestamp': ts}


def check_bankroll():
    """Validate bankroll.json — betting configuration."""
    print("\n─── 8. BANKROLL CONFIG (bankroll.json) ──────────────────────────")
    path = 'bankroll.json'
    if not os.path.exists(path):
        _ts('bankroll.exists', 'FAIL', 'File not found',
            fix='Create bankroll.json with: {"starting_bankroll": 1000, "unit_size": 10, "edge_cap": 10, "created": "2026-02-20"}')
        return {}

    try:
        with open(path) as f:
            config = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        _ts('bankroll.parse', 'FAIL', f'JSON parse error: {e}',
            fix='Fix JSON syntax in bankroll.json or recreate it.')
        return {}

    _ts('bankroll.parse', 'PASS', 'JSON valid')

    # Required fields
    required = {'starting_bankroll': (100, 100000), 'unit_size': (1, 1000), 'edge_cap': (1, 30)}
    for field, (lo, hi) in required.items():
        val = config.get(field)
        if val is None:
            _ts(f'bankroll.{field}', 'FAIL', f'Missing "{field}" key',
                fix=f'Add "{field}" to bankroll.json')
        else:
            try:
                v = float(val)
                if lo <= v <= hi:
                    _ts(f'bankroll.{field}', 'PASS', f'{field}={v}')
                else:
                    _ts(f'bankroll.{field}', 'WARN', f'{field}={v} outside [{lo}, {hi}]')
            except (ValueError, TypeError):
                _ts(f'bankroll.{field}', 'FAIL', f'{field} non-numeric: {val!r}',
                fix=f'Fix "{field}" value in bankroll.json to be a number.')

    return config


# ══════════════════════════════════════════════════════════════════════════════
#  Section 2: CROSS-DATA CONSISTENCY
# ══════════════════════════════════════════════════════════════════════════════
def check_cross_consistency(stats_info, injuries_info, star_tax_info,
                            rest_info, odds_info, schedule_info):
    """Cross-validate data between feeds."""
    print("\n─── 9. CROSS-DATA CONSISTENCY ────────────────────────────────────")

    stats_teams = stats_info.get('teams', set())
    injury_teams = injuries_info.get('teams', set())
    odds_teams = odds_info.get('team_names', set())
    today_games = schedule_info.get('today_games', [])

    # Injuries reference teams in the stats cache?
    if injury_teams and stats_teams:
        orphan = injury_teams - stats_teams - {'LA Clippers'}
        if orphan:
            _ts('cross.injury_vs_stats', 'FAIL',
                f'{len(orphan)} injury team(s) don\'t match stats cache', list(orphan)[:5],
                fix='Check injury_scraper.py CBS_TEAM_MAP — names must match nba_teams_static.py canonical names.')
        else:
            _ts('cross.injury_vs_stats', 'PASS', 'All injury teams match stats teams')

    # Odds reference canonical names?
    if odds_teams:
        orphan = odds_teams - EXPECTED_TEAMS - {''}
        if orphan:
            _ts('cross.odds_team_names', 'FAIL', f'Odds has non-canonical names: {orphan}',
                fix='Check odds_api.py team name mapping — full names must match nba_teams_static.py.')
        else:
            _ts('cross.odds_team_names', 'PASS', 'All odds teams canonical')

    # Today's scheduled games have odds?
    if today_games:
        odds_games = odds_info.get('games', {})
        missing_odds = []
        for g in today_games:
            away, home = g.get('away', ''), g.get('home', '')
            # Build lookup key (nickname format: "Nickname @ Nickname")
            away_nick = away.split()[-1] if away else ''
            home_nick = home.split()[-1] if home else ''
            found = False
            for key in odds_games:
                if away_nick.lower() in key.lower() and home_nick.lower() in key.lower():
                    found = True
                    break
            if not found:
                missing_odds.append(f'{away} @ {home}')
        if missing_odds:
            _ts('cross.schedule_vs_odds', 'WARN',
                f'{len(missing_odds)} scheduled game(s) without odds',
                missing_odds[:5])
        else:
            _ts('cross.schedule_vs_odds', 'PASS',
                f'All {len(today_games)} scheduled games have odds data')

    # Star tax has entries for today's teams?
    if today_games and star_tax_info.get('teams'):
        from nba_teams_static import TEAM_NAME_TO_ID
        st_teams = star_tax_info['teams']
        missing_st = []
        for g in today_games:
            for role in ('away', 'home'):
                tn = g.get(role, '')
                tid = TEAM_NAME_TO_ID.get(tn)
                if tid and str(tid) not in st_teams:
                    missing_st.append(f'{tn} (ID {tid})')
        if missing_st:
            _ts('cross.schedule_vs_star_tax', 'WARN',
                f'{len(missing_st)} team(s) playing today not in star tax cache',
                list(set(missing_st))[:5])
        else:
            _ts('cross.schedule_vs_star_tax', 'PASS', 'All today\'s teams have star tax data')


# ══════════════════════════════════════════════════════════════════════════════
#  Section 3: MODEL CALCULATION SPOT-CHECK
# ══════════════════════════════════════════════════════════════════════════════
def check_model_calculations(schedule_info, odds_info):
    """Run the prediction model on today's games and validate outputs."""
    print("\n─── 10. MODEL CALCULATION SPOT-CHECK ─────────────────────────────")

    today_games = schedule_info.get('today_games', [])
    odds_games = odds_info.get('games', {})

    if not today_games:
        _ts('model.no_games', 'WARN', 'No games to spot-check')
        return

    # Import model
    try:
        from nba_analytics import predict_nba_spread, calculate_pace_and_ratings
        from nba_engine_ui import calculate_kelly, load_edge_cap
    except ImportError as e:
        _ts('model.import', 'FAIL', f'Cannot import model: {e}',
            fix='Check for syntax errors: python -c "import nba_analytics; import nba_engine_ui"')
        return

    _ts('model.import', 'PASS', 'Model modules loaded')

    # Load ratings once
    try:
        ratings = calculate_pace_and_ratings()
        _ts('model.ratings_load', 'PASS', f'{len(ratings)} teams in ratings DataFrame')
    except Exception as e:
        _ts('model.ratings_load', 'FAIL', f'Ratings failed: {e}',
            fix='Re-run: bash fetch_all_nba_data.sh stats')
        return

    edge_cap = load_edge_cap()
    games_checked = 0
    issues = []

    for g in today_games[:5]:  # Spot-check up to 5 games
        away, home = g.get('away', ''), g.get('home', '')
        try:
            fair_line, q_players, news, flag, star_tax_failed = predict_nba_spread(away, home)
            games_checked += 1

            # Fair line in range?
            if not (SPREAD_RANGE[0] <= fair_line <= SPREAD_RANGE[1]):
                issues.append(f'{away}@{home}: fair_line={fair_line} out of range')

            # Get market line for edge check
            market = None
            for key, od in odds_games.items():
                a_nick = away.split()[-1].lower()
                h_nick = home.split()[-1].lower()
                if a_nick in key.lower() and h_nick in key.lower():
                    market = float(od.get('consensus_line', 0))
                    break

            if market is not None:
                edge = round(abs(fair_line - market), 2)
                kelly = calculate_kelly(market, fair_line)
                capped_edge = min(edge, edge_cap)

                pick = home if fair_line < market else away
                # Sanity: pick should be one of the two teams
                if pick not in (away, home):
                    issues.append(f'{away}@{home}: pick={pick!r} not in matchup!')

                # Kelly in range?
                if not (KELLY_RANGE[0] <= kelly <= KELLY_RANGE[1]):
                    issues.append(f'{away}@{home}: kelly={kelly}% out of range')

                # Edge in range?
                if not (EDGE_RANGE[0] <= edge <= EDGE_RANGE[1]):
                    issues.append(f'{away}@{home}: edge={edge} out of range')

            # Star tax failure should be flagged
            if star_tax_failed:
                issues.append(f'{away}@{home}: star_tax_failed=True')

        except Exception as e:
            issues.append(f'{away}@{home}: model error: {e}')

    _ts('model.spot_check', 'PASS' if not issues else 'WARN',
        f'{games_checked} game(s) checked' + (f', {len(issues)} issue(s)' if issues else ', all clean'),
        issues[:8] if issues else None)


# ══════════════════════════════════════════════════════════════════════════════
#  Section 4: BET TRACKER INTEGRITY
# ══════════════════════════════════════════════════════════════════════════════
def check_bet_tracker():
    """Validate today's bet tracker (deep) and scan all trackers for conformance."""
    print("\n─── 11. BET TRACKER INTEGRITY ────────────────────────────────────")

    today_str = datetime.now().strftime('%Y-%m-%d')

    # ── Part A: All-tracker conformance scan ────────────────────────────────
    canonical_tail = ['ClosingLine', 'CLV', 'PreflightCheck', 'PreflightNote']
    all_trackers = sorted(glob.glob(os.path.join(BASE_DIR, 'bet_tracker_*.csv')))

    if all_trackers:
        conforming = []
        non_conforming = []
        for tp in all_trackers:
            fname = os.path.basename(tp)
            try:
                with open(tp) as f:
                    reader = csv.reader(f)
                    header = next(reader, [])
                    data = list(reader)
            except Exception:
                non_conforming.append((fname, 'unreadable', 0, ''))
                continue

            n_bets = len(data)
            missing_cols = [c for c in canonical_tail if c not in header]

            if missing_cols:
                non_conforming.append((fname, 'missing_cols', n_bets,
                                       f'Missing: {", ".join(missing_cols)}'))
                continue

            # Check preflight stamp / note coverage
            pfc_idx = header.index('PreflightCheck')
            pfn_idx = header.index('PreflightNote')
            stamped = sum(1 for r in data if len(r) > pfc_idx and r[pfc_idx].strip())
            noted = sum(1 for r in data if len(r) > pfn_idx and r[pfn_idx].strip())
            handled = sum(1 for r in data
                          if (len(r) > pfc_idx and r[pfc_idx].strip()) or
                             (len(r) > pfn_idx and r[pfn_idx].strip()))

            if handled == n_bets:
                # Show stamp type: verified (has timestamp) vs historical (note only)
                if stamped == n_bets:
                    status = f'{n_bets} bet(s), all preflight-verified'
                elif stamped > 0:
                    status = f'{n_bets} bet(s), {stamped} verified / {noted - stamped} historical'
                else:
                    status = f'{n_bets} bet(s), historical (noted)'
                conforming.append((fname, status))
            else:
                unhandled = n_bets - handled
                non_conforming.append((fname, 'unstamped', n_bets,
                                       f'{unhandled}/{n_bets} bet(s) have no preflight stamp or note'))

        # Print conformance summary
        total = len(all_trackers)
        n_ok = len(conforming)
        n_bad = len(non_conforming)

        if n_bad == 0:
            _ts('tracker.conformance', 'PASS',
                f'All {total} tracker(s) conforming — columns ✓, preflight stamps ✓')
        else:
            _ts('tracker.conformance', 'WARN',
                f'{n_ok}/{total} conforming, {n_bad} non-conforming',
                fix='Run: python preflight_check.py --backfill')

        # Detail lines for each tracker (printed as sub-items, not counted as checks)
        for fname, status in conforming:
            is_today = today_str in fname
            marker = '📌' if is_today else '  '
            print(f'       {marker} ✅ {fname}: {status}')
        for fname, reason, n_bets, detail in non_conforming:
            is_today = today_str in fname
            marker = '📌' if is_today else '  '
            print(f'       {marker} ⚠️  {fname}: {detail}')
    else:
        _ts('tracker.conformance', 'WARN', 'No bet tracker files found')

    # ── Part B: Deep validation of today's tracker ──────────────────────────
    path = os.path.join(BASE_DIR, f'bet_tracker_{today_str}.csv')
    if not os.path.exists(path):
        _ts('tracker.today', 'WARN', f'No tracker for today ({os.path.basename(path)})')
        return

    with open(path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        _ts('tracker.today', 'WARN', 'Tracker exists but has no rows')
        return

    _ts('tracker.parse', 'PASS', f'{len(rows)} bet(s) in today\'s tracker')

    expected_cols = ['ID', 'Away', 'Home', 'Fair', 'Market', 'Edge', 'Kelly', 'Pick',
                     'Result', 'ClosingLine', 'CLV', 'PreflightCheck', 'PreflightNote']
    cols = list(rows[0].keys())
    missing = [c for c in expected_cols if c not in cols]
    if missing:
        _ts('tracker.columns', 'WARN', f'Missing columns: {missing}',
            fix='Run: python preflight_check.py --backfill')
    else:
        _ts('tracker.columns', 'PASS', 'All expected columns present (incl. preflight)')

    issues = []
    preflight_stamped = 0
    preflight_missing = 0
    for r in rows:
        gid = r.get('ID', '?')
        # Pick matches one of the teams?
        pick = r.get('Pick', '')
        away, home = r.get('Away', ''), r.get('Home', '')
        if pick and pick not in (away, home):
            issues.append(f'{gid}: Pick={pick!r} doesn\'t match Away={away!r} or Home={home!r}')

        # Fair/Market are numeric?
        for field in ('Fair', 'Market'):
            try:
                v = float(r.get(field, ''))
                if not (SPREAD_RANGE[0] <= v <= SPREAD_RANGE[1]):
                    issues.append(f'{gid}: {field}={v} out of range')
            except (ValueError, TypeError):
                if r.get(field):
                    issues.append(f'{gid}: {field}={r.get(field)!r} non-numeric')

        # Edge is non-negative
        try:
            edge = float(r.get('Edge', 0))
            if edge < 0:
                issues.append(f'{gid}: Edge={edge} is negative')
        except (ValueError, TypeError):
            pass

        # Result is valid
        result = r.get('Result', '')
        if result and result not in ('PENDING', 'WIN', 'LOSS', 'PUSH', ''):
            issues.append(f'{gid}: Result={result!r} unexpected')

        # CLV sign: just flags obviously wrong CLVs, not recalculates
        clv_str = r.get('CLV', '')
        if clv_str:
            try:
                clv_val = float(clv_str)
                if abs(clv_val) > 15:
                    issues.append(f'{gid}: CLV={clv_val} unusually large')
            except (ValueError, TypeError):
                issues.append(f'{gid}: CLV={clv_str!r} non-numeric')

        # PreflightCheck tracking
        pf = r.get('PreflightCheck', '')
        if pf:
            preflight_stamped += 1
        else:
            preflight_missing += 1

    if issues:
        _ts('tracker.integrity', 'WARN', f'{len(issues)} issue(s)', issues[:8])
    else:
        _ts('tracker.integrity', 'PASS', 'All bet rows structurally valid')

    # Preflight stamp status
    if 'PreflightCheck' in cols:
        if preflight_missing == 0:
            _ts('tracker.preflight', 'PASS', f'All {preflight_stamped} bet(s) preflight-verified')
        elif preflight_stamped > 0:
            _ts('tracker.preflight', 'WARN', f'{preflight_stamped}/{len(rows)} stamped, {preflight_missing} unstamped',
                fix='Re-run: python preflight_check.py (will stamp on pass)')
        else:
            _ts('tracker.preflight', 'WARN', f'No bets have preflight stamps yet',
                fix='Run: python preflight_check.py (will stamp on pass)')


# ══════════════════════════════════════════════════════════════════════════════
#  PREFLIGHT STAMP & BACKFILL
# ══════════════════════════════════════════════════════════════════════════════
PREFLIGHT_STATUS_FILE = os.path.join(BASE_DIR, '.preflight_status.json')

def _write_preflight_status(passed, checks, warnings, failures):
    """Write a status file so log_bet() can auto-stamp new bets."""
    now = datetime.now()
    status = {
        'passed': passed,
        'date': now.strftime('%Y-%m-%d'),
        'timestamp': now.strftime('%Y-%m-%d %H:%M:%S'),
        'checks': checks,
        'warnings': warnings,
        'failures': failures,
    }
    with open(PREFLIGHT_STATUS_FILE, 'w') as f:
        json.dump(status, f, indent=2)


def _stamp_tracker(tracker_path, preflight_ts, preflight_note):
    """Add or update PreflightCheck and PreflightNote columns in a bet tracker CSV."""
    if not os.path.exists(tracker_path):
        return False

    with open(tracker_path, 'r', newline='') as f:
        reader = csv.reader(f)
        all_rows = list(reader)

    if not all_rows:
        return False

    header = all_rows[0]
    data_rows = all_rows[1:]

    # Add columns if missing
    pfc_idx = header.index('PreflightCheck') if 'PreflightCheck' in header else -1
    pfn_idx = header.index('PreflightNote') if 'PreflightNote' in header else -1

    if pfc_idx == -1:
        header.append('PreflightCheck')
        pfc_idx = len(header) - 1
        for row in data_rows:
            row.append('')
    if pfn_idx == -1:
        header.append('PreflightNote')
        pfn_idx = len(header) - 1
        for row in data_rows:
            row.append('')

    # Stamp each row (only if not already stamped)
    stamped = 0
    for row in data_rows:
        # Ensure row has enough columns
        while len(row) < len(header):
            row.append('')
        if not row[pfc_idx].strip():
            row[pfc_idx] = preflight_ts
            row[pfn_idx] = preflight_note
            stamped += 1

    # Write back
    with open(tracker_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(data_rows)

    return stamped


def stamp_today_tracker():
    """After a successful preflight, stamp today's bet tracker."""
    now = datetime.now()
    today_str = now.strftime('%Y-%m-%d')
    tracker_path = os.path.join(BASE_DIR, f'bet_tracker_{today_str}.csv')
    ts = now.strftime('%Y-%m-%d %H:%M:%S')
    note = f"PASS ({PASS}✓ {WARN}⚠)"

    if os.path.exists(tracker_path):
        stamped = _stamp_tracker(tracker_path, ts, note)
        if stamped:
            print(f"\n  ✅ Stamped {stamped} bet(s) in {os.path.basename(tracker_path)} with preflight pass")
        else:
            print(f"\n  ℹ️  All bets in {os.path.basename(tracker_path)} already stamped")
    else:
        print(f"\n  ℹ️  No tracker for today yet — preflight status saved.")
        print(f"     New bets logged via the engine will be auto-stamped.")


def backfill_trackers():
    """Add PreflightCheck/PreflightNote columns to ALL historical bet trackers.
    Since historical cache data is overwritten daily, we can't retroactively
    validate past trackers — we note the reason in PreflightNote."""
    import re

    print("\n" + "=" * 72)
    print("  PREFLIGHT BACKFILL — Adding columns to historical trackers")
    print("=" * 72)

    files = sorted(glob.glob(os.path.join(BASE_DIR, 'bet_tracker_*.csv')))
    if not files:
        print("  📭 No bet tracker files found.")
        return

    today_str = datetime.now().strftime('%Y-%m-%d')
    updated = 0
    skipped = 0

    for fpath in files:
        fname = os.path.basename(fpath)
        # Extract date from filename
        m = re.search(r'bet_tracker_(\d{4}-\d{2}-\d{2})\.csv', fname)
        tracker_date = m.group(1) if m else None

        with open(fpath, 'r', newline='') as f:
            reader = csv.reader(f)
            all_rows = list(reader)

        if not all_rows:
            continue

        header = all_rows[0]
        data_rows = all_rows[1:]

        # Check if already has the columns AND all rows are populated
        has_pfc = 'PreflightCheck' in header
        has_pfn = 'PreflightNote' in header

        if has_pfc and has_pfn:
            pfc_idx = header.index('PreflightCheck')
            pfn_idx = header.index('PreflightNote')
            # A row is "handled" if it has a timestamp OR a note (historical rows have note only)
            all_handled = all(
                (len(r) > pfc_idx and r[pfc_idx].strip()) or
                (len(r) > pfn_idx and r[pfn_idx].strip())
                for r in data_rows if r
            )
            # Also check that no missing canonical columns need adding
            has_all_cols = all(c in header for c in ('ClosingLine', 'CLV', 'PreflightCheck', 'PreflightNote'))
            if all_handled and has_all_cols:
                print(f"  ⏭️  {fname}: Already fully stamped — skipping")
                skipped += 1
                continue

        # Determine the note based on whether this is today or historical
        if tracker_date == today_str:
            note = 'Added by backfill — run preflight_check.py to validate'
            ts = ''  # Will be filled by a real preflight run
        else:
            note = f'Historical — cache data from {tracker_date} no longer available for retroactive validation'
            ts = ''  # Can't verify, so leave blank

        # Add any missing canonical columns (ClosingLine, CLV, preflight cols)
        for col in ('ClosingLine', 'CLV', 'PreflightCheck', 'PreflightNote'):
            if col not in header:
                header.append(col)
                for row in data_rows:
                    row.append('')

        # Ensure canonical column order: ...ClosingLine,CLV,PreflightCheck,PreflightNote at end
        canonical_tail = ['ClosingLine', 'CLV', 'PreflightCheck', 'PreflightNote']
        other_cols = [c for c in header if c not in canonical_tail]
        new_header = other_cols + canonical_tail
        if new_header != header:
            idx_map = [header.index(c) for c in new_header]
            header = new_header
            data_rows = [[row[i] if i < len(row) else '' for i in idx_map] for row in data_rows]

        pfc_idx = header.index('PreflightCheck')
        pfn_idx = header.index('PreflightNote')

        rows_updated = 0
        for row in data_rows:
            while len(row) < len(header):
                row.append('')
            # Skip rows that already have a stamp or a note
            if not row[pfc_idx].strip() and not row[pfn_idx].strip():
                row[pfc_idx] = ts
                row[pfn_idx] = note
                rows_updated += 1

        with open(fpath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(data_rows)

        print(f"  ✅ {fname}: Updated {rows_updated} row(s)")
        updated += 1

    print(f"\n  Done: {updated} file(s) updated, {skipped} already stamped.")


# ══════════════════════════════════════════════════════════════════════════════
#  Section 5: PIPELINE DEPENDENCY CHECK
# ══════════════════════════════════════════════════════════════════════════════
def check_pipeline_files():
    """Verify all pipeline scripts exist and are importable."""
    print("\n─── 12. PIPELINE FILES & DEPENDENCIES ───────────────────────────")

    critical_scripts = [
        'nba_analytics.py', 'nba_engine_ui.py', 'odds_api.py',
        'injury_scraper.py', 'rest_penalty_scraper.py', 'schedule_scraper.py',
        'star_tax_prefetch.py', 'nba_data_fetcher_advanced.py',
        'update_results.py', 'edge_analyzer.py', 'post_mortem.py',
        'cache_nba_news.py', 'schedule_prefetch.py',
    ]
    missing = [s for s in critical_scripts if not os.path.exists(s)]
    if missing:
        _ts('pipeline.scripts', 'FAIL', f'{len(missing)} missing script(s)', missing,
            fix='Restore from git: git checkout -- ' + ' '.join(missing))
    else:
        _ts('pipeline.scripts', 'PASS', f'All {len(critical_scripts)} pipeline scripts present')

    # Check .env for API key
    env_path = '.env'
    if os.path.exists(env_path):
        with open(env_path) as f:
            env_content = f.read()
        if 'ODDS_API_KEY' in env_content:
            _ts('pipeline.api_key', 'PASS', 'ODDS_API_KEY found in .env')
        else:
            _ts('pipeline.api_key', 'WARN', 'ODDS_API_KEY not found in .env — odds fetching may fail')
    else:
        # Check environment variable
        if os.environ.get('ODDS_API_KEY'):
            _ts('pipeline.api_key', 'PASS', 'ODDS_API_KEY set in environment')
        else:
            _ts('pipeline.api_key', 'WARN', 'No .env file and ODDS_API_KEY not in environment')

    # Check fetch_all_nba_data.sh
    if os.path.exists('fetch_all_nba_data.sh'):
        _ts('pipeline.fetch_script', 'PASS', 'fetch_all_nba_data.sh present')
    else:
        _ts('pipeline.fetch_script', 'FAIL', 'fetch_all_nba_data.sh missing',
            fix='Restore from git: git checkout -- fetch_all_nba_data.sh')

    # Check nba_teams_static.py is internally consistent
    try:
        from nba_teams_static import get_teams, TEAM_ID_TO_NAME, TEAM_NAME_TO_ID
        teams = get_teams()
        if len(teams) == 30 and len(TEAM_ID_TO_NAME) == 30 and len(TEAM_NAME_TO_ID) == 30:
            _ts('pipeline.static_teams', 'PASS', '30 teams in nba_teams_static.py')
        else:
            _ts('pipeline.static_teams', 'FAIL',
                f'teams={len(teams)}, ID_TO_NAME={len(TEAM_ID_TO_NAME)}, NAME_TO_ID={len(TEAM_NAME_TO_ID)}',
                fix='Check nba_teams_static.py — must have exactly 30 NBA teams.')
    except Exception as e:
        _ts('pipeline.static_teams', 'FAIL', f'Import error: {e}',
            fix='Fix syntax error in nba_teams_static.py')


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════
def main():
    quick = '--quick' in sys.argv
    fix = '--fix' in sys.argv
    backfill = '--backfill' in sys.argv

    # ── Backfill mode: add columns to all historical trackers and exit ────
    if backfill:
        backfill_trackers()
        return 0

    print("=" * 72)
    print("  NBA PREDICTION ENGINE — PRE-FLIGHT CHECK")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 72)

    # Section 1: Data feeds
    stats_info = check_stats_cache()
    injuries_info = check_injuries_cache()
    star_tax_info = check_star_tax_cache()
    rest_info = check_rest_penalty_cache()
    odds_info = check_odds_cache()
    schedule_info = check_schedule_cache()
    news_info = check_news_cache()
    bankroll_info = check_bankroll()

    if not quick:
        # Section 2: Cross-consistency
        check_cross_consistency(stats_info, injuries_info, star_tax_info,
                                rest_info, odds_info, schedule_info)

        # Section 3: Model spot-check
        check_model_calculations(schedule_info, odds_info)

        # Section 4: Bet tracker
        check_bet_tracker()

    # Section 5: Pipeline files (always)
    check_pipeline_files()

    # ── Summary ───────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    total = PASS + WARN + FAIL
    print(f"  RESULTS: {PASS} PASS | {WARN} WARN | {FAIL} FAIL  ({total} checks)")
    if FAIL == 0 and WARN == 0:
        print("  🟢 ALL CLEAR — Safe to run the model and place bets")
    elif FAIL == 0:
        print("  🟡 WARNINGS ONLY — Review flagged items before betting")
    else:
        print("  🔴 FAILURES DETECTED — Fix before placing any bets")
    print("=" * 72)

    # ── Remediation Guide ─────────────────────────────────────────────────
    if FAIL_DETAILS:
        print("\n┌──────────────────────────────────────────────────────────────────┐")
        print("│  🔧  HOW TO FIX                                                 │")
        print("├──────────────────────────────────────────────────────────────────┤")
        for i, (label, msg, fix_hint) in enumerate(FAIL_DETAILS, 1):
            print(f"│  {i}. ❌ {label}")
            print(f"│     Problem: {msg}")
            print(f"│     Fix:     {fix_hint}")
            if i < len(FAIL_DETAILS):
                print("│")
        print("├──────────────────────────────────────────────────────────────────┤")
        print("│  💡 Quick fix for most data issues:                              │")
        print("│     bash fetch_all_nba_data.sh                                   │")
        print("│     python preflight_check.py          (re-verify)               │")
        print("│                                                                  │")
        print("│  💡 If a scraper format changed:                                 │")
        print("│     1. Open the scraper file mentioned in the fix                │")
        print("│     2. Check the CSS selectors / API response format             │")
        print("│     3. Fix the parsing, re-run the scraper                       │")
        print("│     4. Re-run: python preflight_check.py                         │")
        print("└──────────────────────────────────────────────────────────────────┘")

    if WARN_DETAILS and not FAIL_DETAILS:
        print("\n┌──────────────────────────────────────────────────────────────────┐")
        print("│  📋  WARNINGS TO REVIEW                                         │")
        print("├──────────────────────────────────────────────────────────────────┤")
        for i, (label, msg, fix_hint) in enumerate(WARN_DETAILS, 1):
            print(f"│  {i}. ⚠️  {label}")
            print(f"│     {msg}")
            print(f"│     Suggestion: {fix_hint}")
            if i < len(WARN_DETAILS):
                print("│")
        print("└──────────────────────────────────────────────────────────────────┘")

    # ── Write preflight status file (for log_bet auto-stamping) ───────────
    _write_preflight_status(
        passed=(FAIL == 0),
        checks=PASS,
        warnings=WARN,
        failures=FAIL,
    )

    # ── Stamp today's tracker on pass ─────────────────────────────────────
    if FAIL == 0:
        stamp_today_tracker()

    # Auto-fix mode
    if fix and FAIL > 0:
        print("\n  🔧 --fix mode: Attempting to re-run data scrapers...")
        try:
            print("  Running: bash fetch_all_nba_data.sh")
            result = subprocess.run(
                ['bash', 'fetch_all_nba_data.sh'],
                capture_output=True, text=True, timeout=300
            )
            if result.returncode == 0:
                print("  ✅ Data refresh complete. Re-run preflight_check.py to verify.")
            else:
                print(f"  ❌ fetch_all_nba_data.sh failed: {result.stderr[:200]}")
        except subprocess.TimeoutExpired:
            print("  ❌ Timed out after 5 minutes")
        except Exception as e:
            print(f"  ❌ Error: {e}")

    return 1 if FAIL > 0 else 0


if __name__ == '__main__':
    sys.exit(main())
