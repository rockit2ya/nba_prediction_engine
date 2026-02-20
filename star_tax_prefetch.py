"""
NBA Star Tax Prefetcher
Scrapes player advanced stats (NET_RATING) from NBA.com using Selenium,
then caches per-team player impact data for offline use in nba_analytics.py.

NET_RATING is used as a proxy for On/Off impact — it measures how much
better or worse the team performs per 100 possessions when that player is active.

Primary: Selenium scrape of NBA.com /stats/players/advanced (same method as
         nba_data_fetcher_advanced.py which already works)
Fallback: none needed — if NBA.com is down, cache is simply not generated
          and the UI degrades gracefully with a warning.

Writes: nba_star_tax_cache.json
Run standalone or via fetch_all_nba_data.sh:
  python star_tax_prefetch.py
"""

import json
import time
import os
from datetime import datetime

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'nba_star_tax_cache.json')
NBA_PLAYER_ADV_URL = "https://www.nba.com/stats/players/advanced"

# Canonical team name -> NBA team ID (static lookup, no nba_api needed)
TEAM_NAME_TO_ID = {
    'Atlanta Hawks': 1610612737, 'Boston Celtics': 1610612738,
    'Brooklyn Nets': 1610612751, 'Charlotte Hornets': 1610612766,
    'Chicago Bulls': 1610612741, 'Cleveland Cavaliers': 1610612739,
    'Dallas Mavericks': 1610612742, 'Denver Nuggets': 1610612743,
    'Detroit Pistons': 1610612765, 'Golden State Warriors': 1610612744,
    'Houston Rockets': 1610612745, 'Indiana Pacers': 1610612754,
    'LA Clippers': 1610612746, 'Los Angeles Clippers': 1610612746,
    'Los Angeles Lakers': 1610612747, 'Memphis Grizzlies': 1610612763,
    'Miami Heat': 1610612748, 'Milwaukee Bucks': 1610612749,
    'Minnesota Timberwolves': 1610612750, 'New Orleans Pelicans': 1610612740,
    'New York Knicks': 1610612752, 'Oklahoma City Thunder': 1610612760,
    'Orlando Magic': 1610612753, 'Philadelphia 76ers': 1610612755,
    'Phoenix Suns': 1610612756, 'Portland Trail Blazers': 1610612757,
    'Sacramento Kings': 1610612758, 'San Antonio Spurs': 1610612759,
    'Toronto Raptors': 1610612761, 'Utah Jazz': 1610612762,
    'Washington Wizards': 1610612764,
}
TEAM_ID_TO_NAME = {v: k for k, v in TEAM_NAME_TO_ID.items() if k != 'LA Clippers'}

# Map NBA.com team abbreviations to full names
ABBREV_TO_FULL = {
    'ATL': 'Atlanta Hawks', 'BOS': 'Boston Celtics', 'BKN': 'Brooklyn Nets',
    'CHA': 'Charlotte Hornets', 'CHI': 'Chicago Bulls', 'CLE': 'Cleveland Cavaliers',
    'DAL': 'Dallas Mavericks', 'DEN': 'Denver Nuggets', 'DET': 'Detroit Pistons',
    'GSW': 'Golden State Warriors', 'GS': 'Golden State Warriors',
    'HOU': 'Houston Rockets', 'IND': 'Indiana Pacers',
    'LAC': 'Los Angeles Clippers', 'LAL': 'Los Angeles Lakers',
    'MEM': 'Memphis Grizzlies', 'MIA': 'Miami Heat', 'MIL': 'Milwaukee Bucks',
    'MIN': 'Minnesota Timberwolves', 'NOP': 'New Orleans Pelicans',
    'NO': 'New Orleans Pelicans', 'NYK': 'New York Knicks',
    'NY': 'New York Knicks', 'OKC': 'Oklahoma City Thunder',
    'ORL': 'Orlando Magic', 'PHI': 'Philadelphia 76ers',
    'PHX': 'Phoenix Suns', 'PHO': 'Phoenix Suns',
    'POR': 'Portland Trail Blazers', 'SAC': 'Sacramento Kings',
    'SAS': 'San Antonio Spurs', 'SA': 'San Antonio Spurs',
    'TOR': 'Toronto Raptors', 'UTA': 'Utah Jazz',
    'WAS': 'Washington Wizards', 'WSH': 'Washington Wizards',
}


def resolve_team_id(team_text):
    """Resolve a team name/abbreviation to team ID."""
    team_text = team_text.strip()
    # Try abbreviation first
    if team_text.upper() in ABBREV_TO_FULL:
        full = ABBREV_TO_FULL[team_text.upper()]
        return TEAM_NAME_TO_ID.get(full)
    # Try full name
    if team_text in TEAM_NAME_TO_ID:
        return TEAM_NAME_TO_ID[team_text]
    # Fuzzy: check if any full name contains this
    for full, tid in TEAM_NAME_TO_ID.items():
        if team_text.lower() in full.lower():
            return tid
    return None


def fetch_via_selenium():
    """Scrape player advanced stats (NET_RATING) from NBA.com using Selenium.
    Same approach as nba_data_fetcher_advanced.py (proven to work).
    Returns dict: { team_id_str: { player_name_lower: net_rating, ... }, ... }"""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument(
        'user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
    )

    driver = webdriver.Chrome(options=options)
    results = {}

    try:
        print("  Loading NBA.com player advanced stats...")
        driver.get(NBA_PLAYER_ADV_URL)
        time.sleep(2)

        # Scroll to trigger lazy loading (same as nba_data_fetcher_advanced.py)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3)

        # Handle cookie popup
        try:
            WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((By.XPATH,
                    "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
                    "'abcdefghijklmnopqrstuvwxyz'), 'accept')]"))
            ).click()
            time.sleep(1)
        except Exception:
            pass

        # Expand table to show all players
        try:
            # NBA.com uses a <select> for page size — find it and pick "All" (-1)
            selects = driver.find_elements(By.TAG_NAME, "select")
            paginated = False
            for sel_el in selects:
                from selenium.webdriver.support.ui import Select
                sel = Select(sel_el)
                opts = sel.options
                for opt in opts:
                    val = opt.get_attribute('value')
                    txt = opt.text.strip().lower()
                    if val == '-1' or txt == 'all':
                        sel.select_by_value(opt.get_attribute('value'))
                        paginated = True
                        break
                if paginated:
                    break
            if paginated:
                time.sleep(4)
                print("  Expanded to show all players")
            else:
                # Fallback: page through all pages and accumulate rows
                print("  [INFO] No 'All' option found — will paginate through pages")
        except Exception:
            print("  [WARN] Could not paginate to 'All' — scraping visible page only")

        # Scroll again after pagination change
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)

        # Find the stats table (same class as nba_data_fetcher_advanced.py)
        table = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CLASS_NAME, "Crom_table__p1iZz"))
        )
        rows = table.find_elements(By.TAG_NAME, "tr")
        header_row = rows[0].find_elements(By.TAG_NAME, "th")
        headers = [h.text.strip().upper() for h in header_row]

        print(f"  Found {len(rows) - 1} player rows")
        print(f"  Headers: {headers[:10]}...")

        # Find column indices
        def find_idx(name):
            for i, h in enumerate(headers):
                if name in h:
                    return i
            return -1

        player_idx = find_idx('PLAYER')
        team_idx = find_idx('TEAM')
        net_idx = find_idx('NETRTG')
        if net_idx == -1:
            net_idx = find_idx('NET')

        if player_idx == -1 or team_idx == -1 or net_idx == -1:
            print(f"  [ERROR] Missing columns. PLAYER={player_idx}, TEAM={team_idx}, NET={net_idx}")
            print(f"  Full headers: {headers}")
            return {}

        for row in rows[1:]:
            cols = row.find_elements(By.TAG_NAME, "td")
            if len(cols) <= max(player_idx, team_idx, net_idx):
                continue
            try:
                player_name = cols[player_idx].text.strip()
                team_abbrev = cols[team_idx].text.strip()
                net_text = cols[net_idx].text.strip()

                if not player_name or not team_abbrev or not net_text:
                    continue

                net_rating = float(net_text)
                team_id = resolve_team_id(team_abbrev)
                if not team_id:
                    continue

                tid_str = str(team_id)
                if tid_str not in results:
                    results[tid_str] = {}

                results[tid_str][player_name.lower()] = net_rating

            except (ValueError, IndexError):
                continue

        team_count = len(results)
        player_count = sum(len(v) for v in results.values())
        print(f"  Scraped {player_count} players across {team_count} teams")

    except Exception as e:
        print(f"  [ERROR] Selenium scrape failed: {e}")
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    return results


def fetch_all_star_tax():
    """Fetch player impact data and write cache."""
    selenium_data = fetch_via_selenium()

    if not selenium_data:
        print("\n  [WARN] No data scraped. Star tax cache NOT generated.")
        print("  The UI will still work — star tax will show as unavailable.")
        return 0

    # Build final cache
    all_team_ids = set(str(tid) for tid in TEAM_ID_TO_NAME.keys())
    cache = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'source': 'NBA.com (Selenium)',
        'metric': 'NET_RATING',
        'lookup_by': 'player_name',
        'teams': {}
    }

    success_count = 0
    for tid_str in sorted(all_team_ids):
        team_name = TEAM_ID_TO_NAME.get(int(tid_str), f'Team {tid_str}')
        players = selenium_data.get(tid_str, {})
        entry = {'team_name': team_name, 'players': players}
        if not players:
            entry['error'] = 'No data scraped'
        else:
            success_count += 1
        cache['teams'][tid_str] = entry

    with open(CACHE_FILE, 'w') as f:
        json.dump(cache, f, indent=2)

    total_players = sum(len(t.get('players', {})) for t in cache['teams'].values())
    print(f"\nCached star tax data for {success_count} teams ({total_players} players) to {os.path.basename(CACHE_FILE)}")
    return success_count


if __name__ == '__main__':
    print("🏀 NBA Star Tax Prefetcher")
    print("=" * 50)
    fetch_all_star_tax()
