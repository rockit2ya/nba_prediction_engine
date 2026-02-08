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

# --- BROWSER SETTINGS & SESSION ---
# Persistent session keeps the connection open for massive speed gains
session = requests.Session()
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
    """Hardened fetcher with Baseline Fallback."""
    if not force_refresh and os.path.exists(CACHE_FILE):
        return pd.read_json(CACHE_FILE)

    for attempt in range(2):
        try:
            adv = leaguedashteamstats.LeagueDashTeamStats(
                season=season, last_n_games=last_n_games, 
                measure_type_detailed_defense='Advanced', headers=HEADERS, timeout=12
            ).get_data_frames()[0]
            
            if not adv.empty:
                adv.to_json(CACHE_FILE)
                with open(TIMESTAMP_FILE, 'w') as f:
                    f.write(datetime.now().strftime("%I:%M %p"))
                return adv[['TEAM_ID', 'TEAM_NAME', 'OFF_RATING', 'DEF_RATING', 'NET_RATING', 'PACE']]
        except Exception:
            time.sleep(1)

    if os.path.exists(CACHE_FILE): return pd.read_json(CACHE_FILE)
    
    # EMERGENCY FALLBACK
    all_nba_teams = teams.get_teams()
    baseline_list = [{'TEAM_ID': t['id'], 'TEAM_NAME': t['full_name'], **LEAGUE_BASELINE} for t in all_nba_teams]
    return pd.DataFrame(baseline_list)

def get_live_injuries():
    """Scrapes CBS Sports for real-time injury statuses."""
    try:
        url = "https://www.cbssports.com/nba/injuries/"
        res = session.get(url, timeout=10) # Using persistent session
        soup = BeautifulSoup(res.content, 'html.parser')
        injury_map = {}
        teams_html = soup.find_all('div', class_='TeamLogoNameLockup-name')
        tables = soup.find_all('table', class_='TableBase-table')
        for team, table in zip(teams_html, tables):
            t_name = team.text.strip()
            statuses = [{'name': r.find_all('td')[0].text.strip(), 
                         'status': r.find_all('td')[4].text.strip().lower()} 
                        for r in table.find_all('tr')[1:]]
            injury_map[t_name] = statuses
        return injury_map
    except: return {}

def get_star_tax_weighted(team_id, out_players):
    """Calculates player impact using On-Off splits."""
    if not out_players: return 0
    weights = {'out': 1.0, 'doubtful': 0.9, 'questionable': 0.5, 'probable': 0.1}
    total_tax = 0
    try:
        on_off = teamplayeronoffsummary.TeamPlayerOnOffSummary(team_id=team_id, headers=HEADERS).get_data_frames()[1]
        active_p = players.get_active_players()
        for p_info in out_players:
            weight = next((v for k, v in weights.items() if k in p_info['status']), 0)
            p_id = next((p['id'] for p in active_p if p['full_name'].lower() == p_info['name'].lower()), None)
            if p_id and weight > 0:
                p_impact = on_off[on_off['PLAYER_ID'] == p_id]['ON_COURT_PLUS_MINUS'].values
                if len(p_impact) > 0: total_tax += (p_impact[0] * weight)
        return round(total_tax / 2, 2)
    except: return 0

def get_rest_penalty(team_id):
    """Determines if a team is on a B2B."""
    try:
        log = teamgamelog.TeamGameLog(team_id=team_id, headers=HEADERS).get_data_frames()[0]
        last_date = datetime.strptime(log.iloc[0]['GAME_DATE'], '%b %d, %Y')
        return -2.5 if (datetime.now() - last_date).days <= 1 else 0
    except: return 0

def predict_nba_spread(away_team, home_team, force_refresh=False):
    """
    Main Logic Engine: 
    Uses Multi-threading to fetch situational data in parallel.
    """
    ratings = calculate_pace_and_ratings(force_refresh=force_refresh)
    
    # Fuzzy Matching
    try:
        h_row = ratings[ratings['TEAM_NAME'].str.contains(home_team, case=False)].iloc[0]
        a_row = ratings[ratings['TEAM_NAME'].str.contains(away_team, case=False)].iloc[0]
    except: raise Exception(f"Fuzzy match failed for {away_team} or {home_team}")

    # SPEED UP: Parallel Execution for Situational Checks
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_injuries = executor.submit(get_live_injuries)
        future_h_rest = executor.submit(get_rest_penalty, h_row['TEAM_ID'])
        future_a_rest = executor.submit(get_rest_penalty, a_row['TEAM_ID'])
        
        injuries = future_injuries.result()
        h_rest = future_h_rest.result()
        a_rest = future_a_rest.result()

    # Calculate Bayesian Star Tax
    h_tax = get_star_tax_weighted(h_row['TEAM_ID'], injuries.get(h_row['TEAM_NAME'], []))
    a_tax = get_star_tax_weighted(a_row['TEAM_ID'], injuries.get(a_row['TEAM_NAME'], []))
    
    # Core Math
    rest_adj = h_rest - a_rest
    hca = 3.0 + ((h_row['NET_RATING'] - a_row['NET_RATING']) / 20)
    raw_diff = (h_row['OFF_RATING'] - a_row['DEF_RATING']) - (a_row['OFF_RATING'] - h_row['DEF_RATING'])
    fair_line = (raw_diff * (h_row['PACE'] / 100)) + hca + rest_adj - h_tax + a_tax
    
    q_players = [p['name'] for p in (injuries.get(h_row['TEAM_NAME'], []) + injuries.get(a_row['TEAM_NAME'], [])) if 'questionable' in p['status']]
    return round(fair_line, 2), q_players

def log_bet(gid, away, home, f_line, m_line, edge, rec, kelly):
    filename = f"bet_tracker_{datetime.now().strftime('%Y-%m-%d')}.csv"
    exists = os.path.isfile(filename)
    with open(filename, 'a', newline='') as f:
        writer = csv.writer(f)
        if not exists: writer.writerow(['ID','Away','Home','Fair','Market','Edge','Kelly','Pick','Result'])
        writer.writerow([gid, away, home, f_line, m_line, edge, f"{kelly}%", rec, 'PENDING'])
