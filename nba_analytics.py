import pandas as pd
import requests
import time
import os
import csv
import json
from bs4 import BeautifulSoup
from datetime import datetime
from nba_api.stats.endpoints import leaguedashteamstats, teamgamelog, teamplayeronoffsummary
from nba_api.stats.static import teams, players
import difflib

# --- BROWSER SETTINGS & SESSION ---
# Persistent session keeps the connection open for massive speed gains
session = requests.Session()
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure retry strategy for NBA API reliability
retry_strategy = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
)
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("http://", adapter)
session.mount("https://", adapter)

HEADERS = {
    'Host': 'stats.nba.com',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.5',
    'Referer': 'https://www.nba.com/',
    'Connection': 'keep-alive',
}


CACHE_FILE = "nba_stats_cache.json"
LEAGUE_BASELINE = {'OFF_RATING': 115.5, 'DEF_RATING': 115.5, 'PACE': 99.2, 'NET_RATING': 0.0}

def get_cache_times():
    times = {}
    # Stats cache
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                stats_cache = json.load(f)
            times['stats'] = stats_cache.get('timestamp', 'Unknown')
        except Exception:
            times['stats'] = 'Unknown'
    else:
        times['stats'] = 'Missing'
    # Injuries cache
    if os.path.exists('nba_injuries.csv'):
        try:
            with open('nba_injuries.csv', 'r') as f:
                first_line = f.readline()
            if first_line.startswith('# timestamp:'):
                times['injuries'] = first_line.strip().split(':', 1)[1].strip()
            else:
                times['injuries'] = 'Unknown'
        except Exception:
            times['injuries'] = 'Unknown'
    else:
        times['injuries'] = 'Missing'
    # News cache
    if os.path.exists('nba_news_cache.json'):
        try:
            with open('nba_news_cache.json', 'r') as f:
                news_cache = json.load(f)
            times['news'] = news_cache.get('timestamp', 'Unknown')
        except Exception:
            times['news'] = 'Unknown'
    else:
        times['news'] = 'Missing'
    # Rest penalty cache
    if os.path.exists('nba_rest_penalty_cache.csv'):
        try:
            with open('nba_rest_penalty_cache.csv', 'r') as f:
                first_line = f.readline()
            if first_line.startswith('# timestamp:'):
                times['rest'] = first_line.strip().split(':', 1)[1].strip()
            else:
                times['rest'] = 'Unknown'
        except Exception:
            times['rest'] = 'Unknown'
    else:
        times['rest'] = 'Missing'
    return times

def calculate_pace_and_ratings(season='2025-26', last_n_games=10, force_refresh=False):
    """
    Fetches team stats from cache or live API.
    
    NOTE: The NBA Stats API times out frequently. For best results:
    1. Use cached data (default behavior)
    2. Manually refresh when available (force_refresh=True)
    3. Run create_sample_cache.py to update with new data
    """
    # Prefer cached data (most reliable)
    if not force_refresh and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                cache = json.load(f)
            df = pd.DataFrame(cache['data'])
            # Convert dict-of-dicts to DataFrame
            df = pd.DataFrame({col: list(col_dict.values()) for col, col_dict in cache['data'].items()})
            if 'TEAM_ID' not in df.columns:
                all_nba_teams = teams.get_teams()
                name_to_id = {t['full_name']: t['id'] for t in all_nba_teams}
                df['TEAM_ID'] = df['TEAM_NAME'].map(name_to_id)
            cache_time = get_cache_times()['stats']
            print(f"[✓] Using cached team stats (from {cache_time})")
            return df
        except Exception as e:
            print(f"[!] Cache corrupted, attempting fresh fetch...")

    # Only use cached data for stats
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                cache = json.load(f)
            df = pd.DataFrame({col: list(col_dict.values()) for col, col_dict in cache['data'].items()})
            cache_time = get_cache_times()['stats']
            print(f"[✓] Using cached team stats (from {cache_time})")
            return df
        except Exception as e:
            print(f"[!] Cache corrupted, unable to load stats.")
            pass
    # Last resort: baseline (should rarely reach here)
    print("[✗] Unable to fetch cached data. Using baseline fallback.")
    all_nba_teams = teams.get_teams()
    baseline_list = [{'TEAM_ID': t['id'], 'TEAM_NAME': t['full_name'], **LEAGUE_BASELINE} for t in all_nba_teams]
    return pd.DataFrame(baseline_list)

def get_injuries():
    """Load injury data from nba_injuries.csv cache."""
    if not os.path.exists("nba_injuries.csv"):
        print("[✗] No cached injury data found. Run: bash fetch_all_nba_data.sh")
        return {}
    try:
        injuries_df = pd.read_csv("nba_injuries.csv")
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
    """Calculates player impact using On-Off splits."""
    if not out_players: return 0
    weights = {'out': 1.0, 'doubtful': 0.9, 'questionable': 0.5, 'probable': 0.1}
    total_tax = 0
    try:
        on_off = teamplayeronoffsummary.TeamPlayerOnOffSummary(team_id=team_id, headers=HEADERS, timeout=8).get_data_frames()[1]
        active_p = players.get_active_players()
        for p_info in out_players:
            weight = next((v for k, v in weights.items() if k in p_info['status']), 0)
            p_id = next((p['id'] for p in active_p if p['full_name'].lower() == p_info['name'].lower()), None)
            if p_id and weight > 0:
                p_impact = on_off[on_off['PLAYER_ID'] == p_id]['ON_COURT_PLUS_MINUS'].values
                if len(p_impact) > 0: total_tax += (p_impact[0] * weight)
        return round(total_tax / 2, 2)
    except:
        return 0

def get_rest_penalty(team_id):
    """Determines if a team is on a B2B."""
    # Use cached rest penalty data
    try:
        import pandas as pd
        all_nba_teams = teams.get_teams()
        id_to_name = {t['id']: t['full_name'] for t in all_nba_teams}
        team_name = id_to_name.get(team_id, None)
        if not team_name:
            return 0
        # Skip header comment line if present
        with open('nba_rest_penalty_cache.csv', 'r') as f:
            lines = f.readlines()
        if lines[0].startswith('#'):
            lines = lines[1:]
        from io import StringIO
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
        'Clippers': 'LA Clippers',
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
    except: raise Exception(f"Fuzzy match failed for {away_team} or {home_team}")

    # Load all cached situational data
    injuries = get_injuries()
    h_rest = get_rest_penalty(h_row['TEAM_ID'])
    a_rest = get_rest_penalty(a_row['TEAM_ID'])
    news = get_news()

    # Flag if any player status is 'out', 'late scratch', or 'day-to-day' for today
    flag = False
    today = datetime.now().strftime('%b %d')
    for team, plist in injuries.items():
        for p in plist:
            if p['status'] in ['out', 'late scratch', 'day-to-day'] and today in p.get('date', ''):
                flag = True
    # Also flag if news contains late scratch
    for item in news:
        if 'late scratch' in item.get('title', '').lower() or 'late scratch' in item.get('summary', '').lower():
            flag = True

    # Calculate Bayesian Star Tax
    h_tax = get_star_tax_weighted(h_row['TEAM_ID'], injuries.get(h_row['TEAM_NAME'], []))
    a_tax = get_star_tax_weighted(a_row['TEAM_ID'], injuries.get(a_row['TEAM_NAME'], []))
    # News factor: late scratches and coaching changes
    news_factor = 0
    for item in news:
        if 'late scratch' in item['title'].lower() or 'late scratch' in item['summary'].lower():
            news_factor -= 2
        if 'coach fired' in item['title'].lower() or 'coach fired' in item['summary'].lower():
            news_factor -= 1
    # Core Math
    rest_adj = h_rest - a_rest
    hca = 3.0 + ((h_row['NET_RATING'] - a_row['NET_RATING']) / 20)
    raw_diff = (h_row['OFF_RATING'] - a_row['DEF_RATING']) - (a_row['OFF_RATING'] - h_row['DEF_RATING'])
    fair_line = (raw_diff * (h_row['PACE'] / 100)) + hca + rest_adj - h_tax + a_tax + news_factor
    q_players = [p['name'] for p in (injuries.get(h_row['TEAM_NAME'], []) + injuries.get(a_row['TEAM_NAME'], [])) if 'questionable' in p['status']]
    return round(fair_line, 2), q_players, news, flag

def log_bet(gid, away, home, f_line, m_line, edge, rec, kelly, book='', odds='', bet_amount=''):
    filename = f"bet_tracker_{datetime.now().strftime('%Y-%m-%d')}.csv"
    notes = input("Enter any manual notes/context for this bet (press Enter to skip): ")
    import csv
    import os
    rows = []
    header = ['ID','Away','Home','Fair','Market','Edge','Kelly','Pick','Book','Odds','Bet','Result','Payout','Notes']
    old_header = ['ID','Away','Home','Fair','Market','Edge','Kelly','Pick','Result','Notes']
    # Read existing rows if file exists
    if os.path.isfile(filename):
        with open(filename, 'r', newline='') as f:
            reader = csv.reader(f)
            rows = list(reader)
        # Remove header if present (support old and new format)
        if rows and (rows[0] == header or rows[0] == old_header):
            rows = rows[1:]
    # Remove any existing entry for this game (ID, Away, Home)
    new_row = [gid, away, home, f_line, m_line, edge, f"{kelly}%", rec, book, odds, bet_amount, 'PENDING', '', notes]
    rows = [row for row in rows if not (len(row) >= 3 and row[0] == gid and row[1] == away and row[2] == home)]
    rows.append(new_row)
    # Write back with header
    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
