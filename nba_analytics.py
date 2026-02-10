import pandas as pd
import requests
import time
import os
import csv
import json
from bs4 import BeautifulSoup
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from nba_api.stats.endpoints import leaguedashteamstats, teamgamelog, teamplayeronoffsummary
from nba_api.stats.static import teams, players
# Additional imports for real-time news and fuzzy matching
import difflib
import feedparser

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
TIMESTAMP_FILE = ".stats_timestamp"
LEAGUE_BASELINE = {'OFF_RATING': 115.5, 'DEF_RATING': 115.5, 'PACE': 99.2, 'NET_RATING': 0.0}

def get_cache_time():
    if os.path.exists(TIMESTAMP_FILE):
        with open(TIMESTAMP_FILE, 'r') as f:
            return f.read()
    return "No Cache Found (Baseline Active)"

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
            cached = pd.read_json(CACHE_FILE)
            cache_time = get_cache_time()
            print(f"[✓] Using cached team stats (from {cache_time})")
            return cached
        except Exception as e:
            print(f"[!] Cache corrupted, attempting fresh fetch...")

    # Try nba_api first
    api_success = False
    if force_refresh or not os.path.exists(CACHE_FILE):
        for attempt in range(2):
            try:
                print(f"[...] Fetching live stats from NBA API (attempt {attempt+1}/2)...")
                adv = leaguedashteamstats.LeagueDashTeamStats(
                    season=season, last_n_games=last_n_games, 
                    measure_type_detailed_defense='Advanced', headers=HEADERS, timeout=45
                ).get_data_frames()[0]
                if not adv.empty:
                    adv.to_json(CACHE_FILE)
                    with open(TIMESTAMP_FILE, 'w') as f:
                        f.write(datetime.now().strftime("%I:%M %p"))
                    print("[✓] Retrieved live stats from NBA API")
                    api_success = True
                    return adv[['TEAM_ID', 'TEAM_NAME', 'OFF_RATING', 'DEF_RATING', 'NET_RATING', 'PACE']]
            except Exception as e:
                print(f"[!] API unavailable: {type(e).__name__}")
                time.sleep(2)

    # If nba_api fails, try Selenium fetcher
    if (not api_success) and (force_refresh or not os.path.exists(CACHE_FILE) or os.path.getsize(CACHE_FILE) == 0):
        print("[!] nba_api failed. Trying Selenium data fetcher...")
        try:
            import subprocess
            result = subprocess.run(['python', 'nba_data_fetcher_advanced.py'], capture_output=True, text=True, timeout=90)
            print(result.stdout)
            if os.path.exists(CACHE_FILE) and os.path.getsize(CACHE_FILE) > 0:
                cached = pd.read_json(CACHE_FILE)
                print("[✓] Data fetched via Selenium script.")
                return cached
        except Exception as e:
            print(f"[!] Selenium fetcher failed: {e}")

    # If Selenium fails, try Playwright fetcher
    if (not api_success) and (not os.path.exists(CACHE_FILE) or os.path.getsize(CACHE_FILE) == 0):
        print("[!] Selenium failed. Trying Playwright data fetcher...")
        try:
            import subprocess
            result = subprocess.run(['python', 'nba_data_fetcher_playwright.py'], capture_output=True, text=True, timeout=90)
            print(result.stdout)
            if os.path.exists(CACHE_FILE) and os.path.getsize(CACHE_FILE) > 0:
                cached = pd.read_json(CACHE_FILE)
                print("[✓] Data fetched via Playwright script.")
                return cached
        except Exception as e:
            print(f"[!] Playwright fetcher failed: {e}")

    # Fallback to existing cache
    if os.path.exists(CACHE_FILE):
        try:
            cached = pd.read_json(CACHE_FILE)
            cache_time = get_cache_time()
            print(f"[⚠] All live fetchers failed. Using cached stats (from {cache_time})")
            return cached
        except:
            pass

    # Last resort: baseline (should rarely reach here)
    print("[✗] Unable to fetch live or cached data. Using baseline fallback.")
    print("[→] Suggestion: Run 'python fetch_all_data.sh' to create fresh sample data")
    all_nba_teams = teams.get_teams()
    baseline_list = [{'TEAM_ID': t['id'], 'TEAM_NAME': t['full_name'], **LEAGUE_BASELINE} for t in all_nba_teams]
    return pd.DataFrame(baseline_list)

def get_live_injuries():
    """Scrapes ESPN for real-time injury statuses (updated for 2026 HTML)."""
    url = "https://www.espn.com/nba/injuries"
    try:
        res = session.get(url, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        teams = {}
        # ESPN: Each team section is a logo img, team name (h2), then a table of injuries
        for h2 in soup.find_all('h2'):
            team_name = h2.text.strip()
            table = h2.find_next('table')
            if not table:
                continue
            players = []
            for row in table.find_all('tr')[1:]:
                cols = row.find_all('td')
                if len(cols) >= 5:
                    player = cols[0].text.strip()
                    pos = cols[1].text.strip()
                    date = cols[2].text.strip()
                    status = cols[3].text.strip().lower()
                    note = cols[4].text.strip()
                    players.append({'name': player, 'position': pos, 'date': date, 'status': status, 'note': note})
            teams[team_name] = players
        return teams
    except Exception as e:
        print(f"[!] ESPN injury scrape failed ({type(e).__name__}): {e}")
        return {}

# Placeholder for real-time news integration
def get_real_time_news():
    def check_news_completeness(news_items):
        # Check for late-breaking news or missing updates
        late_news = [item for item in news_items if 'late scratch' in item['title'].lower() or 'late scratch' in item['summary'].lower()]
        if late_news:
            print("[!] Late-breaking news detected:")
            for item in late_news:
                print(f"  {item['title']} | {item['published']}")
        else:
            print("[✓] No late-breaking news found.")
    # Example: Use RSS feeds from ESPN, NBA, or Twitter API
    feeds = [
        'https://www.espn.com/espn/rss/nba/news',
        'https://www.nba.com/rss/nba_news.xml'
    ]
    news_items = []
    for feed_url in feeds:
        d = feedparser.parse(feed_url)
        for entry in d.entries:
            news_items.append({'title': entry.title, 'summary': entry.summary, 'published': entry.published})
    return news_items

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
    try:
        log = teamgamelog.TeamGameLog(team_id=team_id, headers=HEADERS, timeout=8).get_data_frames()[0]
        last_date = datetime.strptime(log.iloc[0]['GAME_DATE'], '%b %d, %Y')
        return -2.5 if (datetime.now() - last_date).days <= 1 else 0
    except: 
        return 0

def predict_nba_spread(away_team, home_team, force_refresh=False):
    """
    Main Logic Engine: 
    Uses Multi-threading to fetch situational data in parallel.
    """
    ratings = calculate_pace_and_ratings(force_refresh=force_refresh)
    # Improved fuzzy matching for team names
    def fuzzy_team_match(name, team_list):
        matches = difflib.get_close_matches(name, team_list, n=1, cutoff=0.7)
        return matches[0] if matches else name
    team_names = ratings['TEAM_NAME'].tolist()
    h_team = fuzzy_team_match(home_team, team_names)
    a_team = fuzzy_team_match(away_team, team_names)
    try:
        h_row = ratings[ratings['TEAM_NAME'] == h_team].iloc[0]
        a_row = ratings[ratings['TEAM_NAME'] == a_team].iloc[0]
    except: raise Exception(f"Fuzzy match failed for {away_team} or {home_team}")

    # SPEED UP: Parallel Execution for Situational Checks (with timeouts)
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_injuries = executor.submit(get_live_injuries)
        future_h_rest = executor.submit(get_rest_penalty, h_row['TEAM_ID'])
        future_a_rest = executor.submit(get_rest_penalty, a_row['TEAM_ID'])
        future_news = executor.submit(get_real_time_news)
        try:
            injuries = future_injuries.result(timeout=10)
        except:
            injuries = {}
        try:
            h_rest = future_h_rest.result(timeout=10)
        except:
            h_rest = 0
        try:
            a_rest = future_a_rest.result(timeout=10)
        except:
            a_rest = 0
        try:
            news = future_news.result(timeout=10)
        except:
            news = []
        # Flag if any player status is 'out', 'late scratch', or 'day-to-day' for today
        flag = False
        today = datetime.now().strftime('%b %d')
        for team, plist in injuries.items():
            for p in plist:
                if (p['status'] in ['out', 'late scratch', 'day-to-day'] and today in p['date']):
                    flag = True
        # Also flag if news contains late scratch
        for item in news:
            if 'late scratch' in item['title'].lower() or 'late scratch' in item['summary'].lower():
                flag = True

    # Calculate Bayesian Star Tax
    h_tax = get_star_tax_weighted(h_row['TEAM_ID'], injuries.get(h_row['TEAM_NAME'], []))
    a_tax = get_star_tax_weighted(a_row['TEAM_ID'], injuries.get(a_row['TEAM_NAME'], []))
    # Placeholder: Factor in real-time news (e.g., late scratches, coaching changes)
    # Example: If news contains 'late scratch' or 'coach fired', adjust fair_line
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

def log_bet(gid, away, home, f_line, m_line, edge, rec, kelly):
    filename = f"bet_tracker_{datetime.now().strftime('%Y-%m-%d')}.csv"
    exists = os.path.isfile(filename)
    # Add manual notes column for context
    notes = input("Enter any manual notes/context for this bet (press Enter to skip): ")
    with open(filename, 'a', newline='') as f:
        writer = csv.writer(f)
        if not exists: writer.writerow(['ID','Away','Home','Fair','Market','Edge','Kelly','Pick','Result','Notes'])
        writer.writerow([gid, away, home, f_line, m_line, edge, f"{kelly}%", rec, 'PENDING', notes])
