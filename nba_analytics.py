import pandas as pd
import os
import csv
import json
from datetime import datetime
from io import StringIO
from nba_teams_static import get_teams, TEAM_ID_TO_NAME, TEAM_NAME_TO_ID
import difflib

STAR_TAX_CACHE_FILE = 'nba_star_tax_cache.json'


CACHE_FILE = "nba_stats_cache.json"
LEAGUE_BASELINE = {'OFF_RATING': 115.5, 'DEF_RATING': 115.5, 'PACE': 99.2, 'NET_RATING': 0.0}

def _normalize_timestamp(raw: str) -> str:
    """Normalize any ISO-ish timestamp to 'YYYY-MM-DD HH:MM:SS' display format."""
    if raw in ('Unknown', 'Missing'):
        return raw
    for fmt in ('%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(raw.strip(), fmt).strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            continue
    return raw  # return as-is if nothing matched

def get_cache_times():
    """Return dict of {cache_name: (normalised_timestamp, source_label)}."""
    times = {}
    # Stats cache  (NBA.com Selenium)
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                stats_cache = json.load(f)
            times['stats'] = (stats_cache.get('timestamp', 'Unknown'),
                              stats_cache.get('source', 'NBA.com'))
        except Exception:
            times['stats'] = ('Unknown', 'NBA.com')
    else:
        times['stats'] = ('Missing', '')
    # Injuries cache  (CBS Sports)
    if os.path.exists('nba_injuries.csv'):
        try:
            with open('nba_injuries.csv', 'r') as f:
                first_line = f.readline()
            if first_line.startswith('# timestamp:'):
                times['injuries'] = (first_line.strip().split(':', 1)[1].strip(),
                                     'CBS Sports')
            else:
                times['injuries'] = ('Unknown', 'CBS Sports')
        except Exception:
            times['injuries'] = ('Unknown', 'CBS Sports')
    else:
        times['injuries'] = ('Missing', '')
    # News cache  (ESPN RSS)
    if os.path.exists('nba_news_cache.json'):
        try:
            with open('nba_news_cache.json', 'r') as f:
                news_cache = json.load(f)
            times['news'] = (news_cache.get('timestamp', 'Unknown'),
                             news_cache.get('source', 'ESPN'))
        except Exception:
            times['news'] = ('Unknown', 'ESPN')
    else:
        times['news'] = ('Missing', '')
    # Rest penalty cache  (ESPN Selenium)
    if os.path.exists('nba_rest_penalty_cache.csv'):
        try:
            with open('nba_rest_penalty_cache.csv', 'r') as f:
                first_line = f.readline()
            if first_line.startswith('# timestamp:'):
                times['rest'] = (first_line.strip().split(':', 1)[1].strip(),
                                 'ESPN')
            else:
                times['rest'] = ('Unknown', 'ESPN')
        except Exception:
            times['rest'] = ('Unknown', 'ESPN')
    else:
        times['rest'] = ('Missing', '')
    # Schedule cache  (ESPN primary / NBA.com fallback)
    if os.path.exists('nba_schedule_cache.json'):
        try:
            with open('nba_schedule_cache.json', 'r') as f:
                sched_cache = json.load(f)
            times['schedule'] = (sched_cache.get('timestamp', 'Unknown'),
                                 sched_cache.get('source', 'ESPN'))
        except Exception:
            times['schedule'] = ('Unknown', 'ESPN')
    else:
        times['schedule'] = ('Missing', '')
    # Star tax cache  (NBA.com Selenium)
    if os.path.exists(STAR_TAX_CACHE_FILE):
        try:
            with open(STAR_TAX_CACHE_FILE, 'r') as f:
                st_cache = json.load(f)
            times['star_tax'] = (st_cache.get('timestamp', 'Unknown'),
                                 st_cache.get('source', 'NBA.com'))
        except Exception:
            times['star_tax'] = ('Unknown', 'NBA.com')
    else:
        times['star_tax'] = ('Missing', '')
    return {k: (_normalize_timestamp(ts), src.split(' (Selenium)')[0] if src else src)
            for k, (ts, src) in times.items()}

def calculate_pace_and_ratings(season='2025-26', last_n_games=10, force_refresh=False):
    """
    Load team stats from the local nba_stats_cache.json file.

    All data is cache-only — no live API calls are made.
    Use force_refresh=True after running fetch_all_nba_data.sh to
    re-read the on-disk cache (e.g. from the [R] Refresh command).
    """
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                cache = json.load(f)
            df = pd.DataFrame({col: list(col_dict.values()) for col, col_dict in cache['data'].items()})
            # Normalize team names (NBA.com uses 'LA Clippers' but everything else uses 'Los Angeles Clippers')
            df['TEAM_NAME'] = df['TEAM_NAME'].replace({'LA Clippers': 'Los Angeles Clippers'})
            if 'TEAM_ID' not in df.columns:
                df['TEAM_ID'] = df['TEAM_NAME'].map(TEAM_NAME_TO_ID)
            cache_time, _ = get_cache_times()['stats']
            label = "Reloaded" if force_refresh else "Using"
            print(f"[✓] {label} cached team stats (from {cache_time})")
            return df
        except Exception as e:
            print(f"[!] Cache corrupted: {e}")

    # Last resort: baseline (should rarely reach here)
    print("[✗] No cached stats found. Using baseline fallback.")
    baseline_list = [{'TEAM_ID': t['id'], 'TEAM_NAME': t['full_name'], **LEAGUE_BASELINE} for t in get_teams()]
    return pd.DataFrame(baseline_list)

def get_injuries():
    """Load injury data from nba_injuries.csv cache."""
    if not os.path.exists("nba_injuries.csv"):
        print("[✗] No cached injury data found. Run: bash fetch_all_nba_data.sh")
        return {}
    try:
        injuries_df = pd.read_csv("nba_injuries.csv", comment='#')
        injuries = {}
        for _, row in injuries_df.iterrows():
            team = row.get('team', row.get('TEAM_NAME', 'Unknown'))
            player_dict = {
                'name': row.get('player', row.get('name', 'Unknown')),
                'position': row.get('position', ''),
                'date': row.get('date', ''),
                'status': row.get('status', ''),
                'note': row.get('note', row.get('injury', ''))
            }
            injuries.setdefault(team, []).append(player_dict)
        return injuries
    except Exception as e:
        print(f"[✗] Failed to load cached injuries: {e}")
        return {}

def get_news():
    """Load news data from nba_news_cache.json cache."""
    if not os.path.exists("nba_news_cache.json"):
        print("[✗] No cached news data found. Run: bash fetch_all_nba_data.sh")
        return []
    try:
        with open("nba_news_cache.json", "r") as f:
            news = json.load(f)
        return news.get('data', [])
    except Exception as e:
        print(f"[✗] Failed to load cached news: {e}")
        return []

def get_star_tax_weighted(team_id, out_players):
    """Calculates player impact using cached On-Off splits.
    Reads from nba_star_tax_cache.json (prefetched by star_tax_prefetch.py).
    Supports both player-name keyed (Selenium) and player-ID keyed (nba_api) caches."""
    if not out_players:
        return 0
    weights = {'out': 1.0, 'doubtful': 0.9, 'questionable': 0.5, 'game time decision': 0.5, 'probable': 0.1, 'day-to-day': 0.5}
    total_tax = 0
    try:
        if not os.path.exists(STAR_TAX_CACHE_FILE):
            print(f"[⚠️  STAR TAX] No cache found. Run: bash fetch_all_nba_data.sh")
            return None
        with open(STAR_TAX_CACHE_FILE, 'r') as f:
            cache = json.load(f)
        team_data = cache.get('teams', {}).get(str(int(team_id)), {})
        player_impacts = team_data.get('players', {})
        if not player_impacts:
            if 'error' in team_data:
                print(f"[⚠️  STAR TAX] Prefetch failed for team {team_id} — injury impact NOT factored.")
                return None
            return 0

        # Detect lookup mode: keys are player names (Selenium) or player IDs (nba_api)
        lookup_by_name = cache.get('lookup_by') == 'player_name'
        # If any key is non-numeric, treat as name-based
        if not lookup_by_name:
            lookup_by_name = any(not k.isdigit() for k in player_impacts.keys())

        for p_info in out_players:
            status_lower = p_info['status'].lower()
            weight = next((v for k, v in weights.items() if k in status_lower), 0)
            if weight <= 0:
                continue

            pm = None
            p_name = p_info['name'].lower()

            if lookup_by_name:
                # Selenium cache: keyed by lowercase player name
                pm = player_impacts.get(p_name)
            else:
                # Legacy: keyed by player ID string — try direct name match fallback
                # (nba_api removed; all new caches use name-based lookup)
                pm = player_impacts.get(p_name)

            if pm is not None:
                total_tax += (float(pm) * weight)

        return round(total_tax / 2, 2)
    except Exception as e:
        print(f"[⚠️  STAR TAX] Cache read error for team {team_id}: {e}")
        return None  # Distinguish failure from 0 impact

def get_rest_penalty(team_id):
    """Determines if a team is on a B2B."""
    # Use cached rest penalty data
    try:
        team_name = TEAM_ID_TO_NAME.get(team_id, None)
        if not team_name:
            return 0
        # Skip header comment line if present
        with open('nba_rest_penalty_cache.csv', 'r') as f:
            lines = f.readlines()
        if not lines:
            return 0
        if lines[0].startswith('#'):
            lines = lines[1:]
        rest_df = pd.read_csv(StringIO(''.join(lines)))
        row = rest_df[rest_df['TEAM_NAME'] == team_name]
        if not row.empty:
            return float(row.iloc[0]['REST_PENALTY'])
        else:
            return 0
    except Exception as e:
        print(f"[!] Rest penalty cache error: {e}")
        return 0

def predict_nba_spread(away_team, home_team, force_refresh=False):
    """
    Main Logic Engine:
    Loads cached data, applies Bayesian Star Tax, fatigue, HCA,
    and late-scratch news adjustments to produce a fair spread.
    """
    ratings = calculate_pace_and_ratings(force_refresh=force_refresh)
    # Map short/abbreviated team names to full names for robust fuzzy matching
    team_names = ratings['TEAM_NAME'].tolist()
    # Build mapping from common short names to full names
    short_to_full = {
        'Hawks': 'Atlanta Hawks',
        'Celtics': 'Boston Celtics',
        'Nets': 'Brooklyn Nets',
        'Hornets': 'Charlotte Hornets',
        'Bulls': 'Chicago Bulls',
        'Cavaliers': 'Cleveland Cavaliers',
        'Mavericks': 'Dallas Mavericks',
        'Nuggets': 'Denver Nuggets',
        'Pistons': 'Detroit Pistons',
        'Warriors': 'Golden State Warriors',
        'Rockets': 'Houston Rockets',
        'Pacers': 'Indiana Pacers',
        'Clippers': 'Los Angeles Clippers',
        'Lakers': 'Los Angeles Lakers',
        'Grizzlies': 'Memphis Grizzlies',
        'Heat': 'Miami Heat',
        'Bucks': 'Milwaukee Bucks',
        'Timberwolves': 'Minnesota Timberwolves',
        'Pelicans': 'New Orleans Pelicans',
        'Knicks': 'New York Knicks',
        'Thunder': 'Oklahoma City Thunder',
        'Magic': 'Orlando Magic',
        '76ers': 'Philadelphia 76ers',
        'Suns': 'Phoenix Suns',
        'Trail Blazers': 'Portland Trail Blazers',
        'Kings': 'Sacramento Kings',
        'Spurs': 'San Antonio Spurs',
        'Raptors': 'Toronto Raptors',
        'Jazz': 'Utah Jazz',
        'Wizards': 'Washington Wizards',
    }
    def fuzzy_team_match(name, team_list):
        # Try direct match, then mapping, then fuzzy
        if name in team_list:
            return name
        if name in short_to_full and short_to_full[name] in team_list:
            return short_to_full[name]
        matches = difflib.get_close_matches(name, team_list, n=1, cutoff=0.7)
        return matches[0] if matches else name
    h_team = fuzzy_team_match(home_team, team_names)
    a_team = fuzzy_team_match(away_team, team_names)
    try:
        h_row = ratings[ratings['TEAM_NAME'] == h_team].iloc[0]
        a_row = ratings[ratings['TEAM_NAME'] == a_team].iloc[0]
    except (IndexError, KeyError):
        raise Exception(f"Fuzzy match failed for {away_team} or {home_team}")

    # Load all cached situational data
    injuries = get_injuries()
    h_rest = get_rest_penalty(h_row['TEAM_ID'])
    a_rest = get_rest_penalty(a_row['TEAM_ID'])
    news = get_news()

    # Flag if any player status indicates out/late scratch/day-to-day for today
    flag = False
    today = datetime.now().strftime('%b %d')
    for team, plist in injuries.items():
        for p in plist:
            status_lower = p['status'].lower()
            date_str = p.get('date', '')
            if status_lower in ['out', 'late scratch', 'day-to-day', 'out for the season'] and (not date_str or today in date_str):
                flag = True
    # Also flag if news contains late scratch
    for item in news:
        if 'late scratch' in item.get('title', '').lower() or 'late scratch' in item.get('summary', '').lower():
            flag = True

    # Calculate Bayesian Star Tax
    h_tax_raw = get_star_tax_weighted(h_row['TEAM_ID'], injuries.get(h_row['TEAM_NAME'], []))
    a_tax_raw = get_star_tax_weighted(a_row['TEAM_ID'], injuries.get(a_row['TEAM_NAME'], []))
    # Track if star tax API failed (None = failure, 0 = no impact)
    star_tax_failed = h_tax_raw is None or a_tax_raw is None
    if star_tax_failed:
        flag = True  # Flag for user to double-check injuries
    h_tax = h_tax_raw if h_tax_raw is not None else 0
    a_tax = a_tax_raw if a_tax_raw is not None else 0
    # News factor: late scratches and coaching changes (scoped to THIS matchup only)
    news_factor = 0
    matchup_keywords = set()
    for name in [h_team, a_team, home_team, away_team]:
        matchup_keywords.add(name.lower())
    # Extract nicknames (last word of full team name, e.g., "Lakers" from "Los Angeles Lakers")
    for name in [h_team, a_team]:
        parts = name.split()
        if parts:
            matchup_keywords.add(parts[-1].lower())
    for item in news:
        combined = item.get('title', '').lower() + ' ' + item.get('summary', '').lower()
        # Only apply penalty if news mentions one of THIS game's teams
        if not any(kw in combined for kw in matchup_keywords):
            continue
        if 'late scratch' in combined:
            news_factor -= 2
        if 'coach fired' in combined:
            news_factor -= 1
    # Core Math
    rest_adj = h_rest - a_rest
    # FIX 1: Flat HCA — NET_RATING is already captured in raw_diff, don't double-count
    hca = 3.0
    # FIX 2: Regression to the mean — blend team ratings toward league average
    # This reflects uncertainty and matches how Vegas prices lines
    REGRESS_FACTOR = 0.75  # 75% team, 25% league baseline
    h_off = (h_row['OFF_RATING'] * REGRESS_FACTOR) + (LEAGUE_BASELINE['OFF_RATING'] * (1 - REGRESS_FACTOR))
    h_def = (h_row['DEF_RATING'] * REGRESS_FACTOR) + (LEAGUE_BASELINE['DEF_RATING'] * (1 - REGRESS_FACTOR))
    a_off = (a_row['OFF_RATING'] * REGRESS_FACTOR) + (LEAGUE_BASELINE['OFF_RATING'] * (1 - REGRESS_FACTOR))
    a_def = (a_row['DEF_RATING'] * REGRESS_FACTOR) + (LEAGUE_BASELINE['DEF_RATING'] * (1 - REGRESS_FACTOR))
    raw_diff = (h_off - a_def) - (a_off - h_def)
    expected_pace = (h_row['PACE'] + a_row['PACE']) / 2
    fair_line = (raw_diff * (expected_pace / 100)) + hca + rest_adj - h_tax + a_tax + news_factor
    q_players = [p['name'] for p in (injuries.get(h_row['TEAM_NAME'], []) + injuries.get(a_row['TEAM_NAME'], [])) if 'questionable' in p['status']]
    # FIX 3: Return star_tax_failed so UI can warn the user
    return round(fair_line, 2), q_players, news, flag, star_tax_failed

def _calc_to_win(odds, bet_amount):
    """Calculate potential payout (To Win) from American odds and stake."""
    try:
        odds = float(odds)
        bet_amount = float(bet_amount)
    except (ValueError, TypeError):
        return ''
    if odds > 0:
        return round(bet_amount * (odds / 100), 2)
    elif odds < 0:
        return round(bet_amount * (100 / abs(odds)), 2)
    return ''

def log_bet(gid, away, home, f_line, m_line, edge, rec, kelly, confidence='', bet_type='Spread', book='', odds='', bet_amount='', raw_edge=None, edge_capped=False):
    now = datetime.now()
    filename = f"bet_tracker_{now.strftime('%Y-%m-%d')}.csv"
    timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
    notes = input("Enter any manual notes/context for this bet (press Enter to skip): ")
    to_win = _calc_to_win(odds, bet_amount)
    if raw_edge is None:
        raw_edge = edge  # backward compat: if not supplied, raw == capped
    rows = []
    header = ['ID','Timestamp','Away','Home','Fair','Market','Edge','Raw_Edge','Edge_Capped','Kelly','Confidence','Pick','Type','Book','Odds','Bet','ToWin','Result','Payout','Notes','ClosingLine','CLV','PreflightCheck','PreflightNote']
    prev_header_22 = ['ID','Timestamp','Away','Home','Fair','Market','Edge','Raw_Edge','Edge_Capped','Kelly','Confidence','Pick','Type','Book','Odds','Bet','ToWin','Result','Payout','Notes','ClosingLine','CLV']
    prev_header_20 = ['ID','Timestamp','Away','Home','Fair','Market','Edge','Raw_Edge','Edge_Capped','Kelly','Confidence','Pick','Type','Book','Odds','Bet','ToWin','Result','Payout','Notes']
    prev_header_18 = ['ID','Timestamp','Away','Home','Fair','Market','Edge','Kelly','Confidence','Pick','Type','Book','Odds','Bet','ToWin','Result','Payout','Notes']
    prev_header_14 = ['ID','Away','Home','Fair','Market','Edge','Kelly','Pick','Book','Odds','Bet','Result','Payout','Notes']
    old_header_10 = ['ID','Away','Home','Fair','Market','Edge','Kelly','Pick','Result','Notes']
    all_known_headers = [header, prev_header_22, prev_header_20, prev_header_18, prev_header_14, old_header_10]
    # Read existing rows if file exists
    if os.path.isfile(filename):
        with open(filename, 'r', newline='') as f:
            reader = csv.reader(f)
            rows = list(reader)
        # Remove header if present (support old formats)
        if rows and rows[0] in all_known_headers:
            rows = rows[1:]
    # Migrate old rows to 24-column format
    migrated_rows = []
    for row in rows:
        if len(row) == 10:
            # Old 10-col: [ID,Away,Home,Fair,Market,Edge,Kelly,Pick,Result,Notes]
            migrated_rows.append([row[0], '', row[1], row[2], row[3], row[4], row[5], row[5], 'NO', row[6], '', row[7], 'Spread', '', '', '', '', row[8], '', row[9] if len(row) > 9 else '', '', '', '', ''])
        elif len(row) == 14:
            # Prev 14-col: [ID,Away,Home,Fair,Market,Edge,Kelly,Pick,Book,Odds,Bet,Result,Payout,Notes]
            migrated_rows.append([row[0], '', row[1], row[2], row[3], row[4], row[5], row[5], 'NO', row[6], '', row[7], 'Spread', row[8], row[9], row[10], _calc_to_win(row[9], row[10]), row[11], row[12], row[13], '', '', '', ''])
        elif len(row) == 18:
            # Prev 18-col: insert Raw_Edge=Edge, Edge_Capped=NO after Edge column (index 6)
            migrated_rows.append(row[:7] + [row[6], 'NO'] + row[7:] + ['', '', '', ''])
        elif len(row) == 20:
            # Prev 20-col: missing ClosingLine,CLV,PreflightCheck,PreflightNote
            migrated_rows.append(row + ['', '', '', ''])
        elif len(row) == 22:
            # Prev 22-col: has ClosingLine,CLV but missing PreflightCheck,PreflightNote
            migrated_rows.append(row + ['', ''])
        else:
            # Ensure row is padded to 24 cols
            migrated_rows.append(row + [''] * max(0, 24 - len(row)))
    rows = migrated_rows

    # ── Check preflight status: if preflight passed today, stamp the new bet ──
    preflight_ts = ''
    preflight_note = ''
    preflight_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.preflight_status.json')
    try:
        if os.path.isfile(preflight_file):
            with open(preflight_file) as pf:
                pf_data = json.load(pf)
            pf_date = pf_data.get('date', '')
            if pf_date == now.strftime('%Y-%m-%d') and pf_data.get('passed'):
                preflight_ts = pf_data.get('timestamp', '')
                preflight_note = f"PASS ({pf_data.get('checks', '?')}✓ {pf_data.get('warnings', 0)}⚠)"
    except (IOError, json.JSONDecodeError, KeyError):
        pass

    # Remove any existing entry for this game (ID, Away, Home)
    capped_str = 'YES' if edge_capped else 'NO'
    new_row = [gid, timestamp, away, home, f_line, m_line, edge, raw_edge, capped_str, f"{kelly}%", confidence, rec, bet_type, book, odds, bet_amount, to_win, 'PENDING', '', notes, '', '', preflight_ts, preflight_note]
    rows = [row for row in rows if not (len(row) >= 4 and row[0] == gid and row[2] == away and row[3] == home)]
    rows.append(new_row)
    # Write back with header
    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
