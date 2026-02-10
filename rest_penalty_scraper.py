# Map ESPN short display names to full NBA team names
SHORT_TO_FULL_TEAM = {
    'Hawks': 'Atlanta Hawks', 'Celtics': 'Boston Celtics', 'Nets': 'Brooklyn Nets',
    'Hornets': 'Charlotte Hornets', 'Bulls': 'Chicago Bulls', 'Cavaliers': 'Cleveland Cavaliers',
    'Mavericks': 'Dallas Mavericks', 'Nuggets': 'Denver Nuggets', 'Pistons': 'Detroit Pistons',
    'Warriors': 'Golden State Warriors', 'Rockets': 'Houston Rockets', 'Pacers': 'Indiana Pacers',
    'Clippers': 'LA Clippers', 'Lakers': 'Los Angeles Lakers', 'Grizzlies': 'Memphis Grizzlies',
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

# Map ESPN team abbreviations to full names
TEAM_MAP = {
    'ATL': 'Atlanta Hawks', 'BOS': 'Boston Celtics', 'BKN': 'Brooklyn Nets',
    'CHA': 'Charlotte Hornets', 'CHI': 'Chicago Bulls', 'CLE': 'Cleveland Cavaliers',
    'DAL': 'Dallas Mavericks', 'DEN': 'Denver Nuggets', 'DET': 'Detroit Pistons',
    'GSW': 'Golden State Warriors', 'HOU': 'Houston Rockets', 'IND': 'Indiana Pacers',
    'LAC': 'LA Clippers', 'LAL': 'Los Angeles Lakers', 'MEM': 'Memphis Grizzlies',
    'MIA': 'Miami Heat', 'MIL': 'Milwaukee Bucks', 'MIN': 'Minnesota Timberwolves',
    'NOP': 'New Orleans Pelicans', 'NYK': 'New York Knicks', 'OKC': 'Oklahoma City Thunder',
    'ORL': 'Orlando Magic', 'PHI': 'Philadelphia 76ers', 'PHX': 'Phoenix Suns',
    'POR': 'Portland Trail Blazers', 'SAC': 'Sacramento Kings', 'SAS': 'San Antonio Spurs',
    'TOR': 'Toronto Raptors', 'UTA': 'Utah Jazz', 'WAS': 'Washington Wizards'
}

def scrape_rest_penalty():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    driver = webdriver.Chrome(options=options)
    driver.get(ESPN_SCOREBOARD_URL)
    html = driver.page_source
    driver.quit()
    soup = BeautifulSoup(html, 'html.parser')
    today = datetime.now().date()
    team_last_game = {}
    # Find all Scoreboard sections
    for scoreboard in soup.find_all('section', class_='Scoreboard'):
        teams = []
        for team_div in scoreboard.find_all('div', class_='ScoreCell__TeamName--shortDisplayName'):
            team_name = team_div.text.strip()
            if team_name:
                teams.append(team_name)
        if len(teams) == 2:
            for team in teams:
                team_last_game[team] = today
    # Calculate rest penalty
    penalty_data = []
    for team, last_game in team_last_game.items():
        days_since = (today - last_game).days
        penalty = -2.5 if days_since == 1 else 0
        # Map ESPN short display name to full NBA team name
        full_team_name = SHORT_TO_FULL_TEAM.get(team, team)
        penalty_data.append({'TEAM_NAME': full_team_name, 'LAST_GAME_DATE': str(last_game), 'REST_PENALTY': penalty})
    df = pd.DataFrame(penalty_data)
    timestamp = datetime.now().isoformat()
    # Write CSV with timestamp as header comment
    with open(REST_CACHE_FILE, "w") as f:
        f.write(f"# timestamp: {timestamp}\n")
        df.to_csv(f, index=False)
    print(f"[✓] Cached rest penalty data for {len(df)} teams to {REST_CACHE_FILE} (timestamp: {timestamp})")

if __name__ == '__main__':
    scrape_rest_penalty()
