# Map ESPN short display names to full NBA team names
SHORT_TO_FULL_TEAM = {
    'Hawks': 'Atlanta Hawks', 'Celtics': 'Boston Celtics', 'Nets': 'Brooklyn Nets',
    'Hornets': 'Charlotte Hornets', 'Bulls': 'Chicago Bulls', 'Cavaliers': 'Cleveland Cavaliers',
    'Mavericks': 'Dallas Mavericks', 'Nuggets': 'Denver Nuggets', 'Pistons': 'Detroit Pistons',
    'Warriors': 'Golden State Warriors', 'Rockets': 'Houston Rockets', 'Pacers': 'Indiana Pacers',
    'Clippers': 'Los Angeles Clippers', 'LA Clippers': 'Los Angeles Clippers',
    'Lakers': 'Los Angeles Lakers', 'LA Lakers': 'Los Angeles Lakers', 'Grizzlies': 'Memphis Grizzlies',
    'Heat': 'Miami Heat', 'Bucks': 'Milwaukee Bucks', 'Timberwolves': 'Minnesota Timberwolves',
    'Pelicans': 'New Orleans Pelicans', 'Knicks': 'New York Knicks', 'Thunder': 'Oklahoma City Thunder',
    'Magic': 'Orlando Magic', '76ers': 'Philadelphia 76ers', 'Suns': 'Phoenix Suns',
    'Trail Blazers': 'Portland Trail Blazers', 'Kings': 'Sacramento Kings', 'Spurs': 'San Antonio Spurs',
    'Raptors': 'Toronto Raptors', 'Jazz': 'Utah Jazz', 'Wizards': 'Washington Wizards'
}
# NBA Rest Penalty Scraper
# Scrapes ESPN NBA scoreboard for recent game dates for each team
# Caches rest penalty data for offline use

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, timedelta

ESPN_SCOREBOARD_URL = 'https://www.espn.com/nba/scoreboard'
REST_CACHE_FILE = 'nba_rest_penalty_cache.csv'

def scrape_rest_penalty():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    driver = webdriver.Chrome(options=options)

    today = datetime.now().date()
    yesterday = today - timedelta(days=1)

    # Scrape YESTERDAY's scoreboard to find teams that played yesterday
    yesterday_url = f"{ESPN_SCOREBOARD_URL}/_/date/{yesterday.strftime('%Y%m%d')}"
    driver.get(yesterday_url)
    html_yesterday = driver.page_source
    soup_yesterday = BeautifulSoup(html_yesterday, 'html.parser')

    teams_played_yesterday = set()
    for scoreboard in soup_yesterday.find_all('section', class_='Scoreboard'):
        for team_div in scoreboard.find_all('div', class_='ScoreCell__TeamName--shortDisplayName'):
            team_name = team_div.text.strip()
            if team_name:
                teams_played_yesterday.add(team_name)

    # Scrape TODAY's scoreboard to find teams playing today
    driver.get(ESPN_SCOREBOARD_URL)
    html_today = driver.page_source
    driver.quit()
    soup_today = BeautifulSoup(html_today, 'html.parser')

    teams_playing_today = set()
    for scoreboard in soup_today.find_all('section', class_='Scoreboard'):
        for team_div in scoreboard.find_all('div', class_='ScoreCell__TeamName--shortDisplayName'):
            team_name = team_div.text.strip()
            if team_name:
                teams_playing_today.add(team_name)

    # Calculate rest penalty: B2B = played yesterday AND playing today
    # Start with ALL 30 teams so teams that aren't on either scoreboard still appear
    penalty_data = []
    all_canonical = set(SHORT_TO_FULL_TEAM.values())  # 30 canonical names
    scraped_teams = teams_playing_today | teams_played_yesterday
    for team in scraped_teams:
        full_team_name = SHORT_TO_FULL_TEAM.get(team, team)
        all_canonical.discard(full_team_name)  # handled via scrape
        is_b2b = team in teams_played_yesterday and team in teams_playing_today
        penalty = -2.5 if is_b2b else 0
        last_game_date = str(yesterday) if team in teams_played_yesterday else ''
        penalty_data.append({'TEAM_NAME': full_team_name, 'LAST_GAME_DATE': last_game_date, 'REST_PENALTY': penalty})
    # Fill remaining teams (didn't play yesterday or today) with 0 penalty
    for full_name in sorted(all_canonical):
        penalty_data.append({'TEAM_NAME': full_name, 'LAST_GAME_DATE': '', 'REST_PENALTY': 0})
    df = pd.DataFrame(penalty_data)
    timestamp = datetime.now().isoformat()
    # Write CSV with timestamp as header comment
    with open(REST_CACHE_FILE, "w") as f:
        f.write(f"# timestamp: {timestamp}\n")
        df.to_csv(f, index=False)
    print(f"[✓] Cached rest penalty data for {len(df)} teams to {REST_CACHE_FILE} (timestamp: {timestamp})")

if __name__ == '__main__':
    scrape_rest_penalty()
