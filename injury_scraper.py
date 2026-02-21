import re
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime

# URL for NBA injury report
INJURY_URL = "https://www.cbssports.com/nba/injuries/"

# CBS Sports uses abbreviated city names — map to full NBA team names
# (must match TEAM_NAME in nba_stats_cache.json, e.g. "Oklahoma City Thunder")
CBS_TEAM_MAP = {
    "Atlanta": "Atlanta Hawks",
    "Boston": "Boston Celtics",
    "Brooklyn": "Brooklyn Nets",
    "Charlotte": "Charlotte Hornets",
    "Chicago": "Chicago Bulls",
    "Cleveland": "Cleveland Cavaliers",
    "Dallas": "Dallas Mavericks",
    "Denver": "Denver Nuggets",
    "Detroit": "Detroit Pistons",
    "Golden St.": "Golden State Warriors",
    "Golden State": "Golden State Warriors",
    "Houston": "Houston Rockets",
    "Indiana": "Indiana Pacers",
    "L.A. Clippers": "Los Angeles Clippers",
    "LA Clippers": "Los Angeles Clippers",
    "L.A. Lakers": "Los Angeles Lakers",
    "LA Lakers": "Los Angeles Lakers",
    "Memphis": "Memphis Grizzlies",
    "Miami": "Miami Heat",
    "Milwaukee": "Milwaukee Bucks",
    "Minnesota": "Minnesota Timberwolves",
    "New Orleans": "New Orleans Pelicans",
    "New York": "New York Knicks",
    "Oklahoma City": "Oklahoma City Thunder",
    "Okla City": "Oklahoma City Thunder",
    "Orlando": "Orlando Magic",
    "Philadelphia": "Philadelphia 76ers",
    "Phoenix": "Phoenix Suns",
    "Portland": "Portland Trail Blazers",
    "Sacramento": "Sacramento Kings",
    "San Antonio": "San Antonio Spurs",
    "Toronto": "Toronto Raptors",
    "Utah": "Utah Jazz",
    "Washington": "Washington Wizards",
}


def _clean_player_name(raw):
    """Fallback: strip concatenated abbreviated+full name if HTML extraction fails."""
    if len(raw) < 4:
        return raw
    for i in range(1, len(raw)):
        candidate = raw[i:]
        if candidate[0].isupper() and ' ' in candidate and len(candidate.split()[0]) >= 2:
            return candidate
    return raw


def fetch_injury_data(url=INJURY_URL):
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    # CBS has per-team sections: TeamName header + TableBase-table
    team_headers = soup.find_all(class_="TeamName")
    tables = soup.find_all("table", {"class": "TableBase-table"})

    if not team_headers or not tables:
        raise ValueError("Injury tables not found on page — CBS layout may have changed.")

    data = []
    now = datetime.now().isoformat()

    for team_el, table in zip(team_headers, tables):
        cbs_name = team_el.get_text(strip=True)
        team_full = CBS_TEAM_MAP.get(cbs_name, cbs_name)

        rows = table.find_all("tr")[1:]  # Skip header row
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 5:
                continue

            # Extract clean player name from CellPlayerName--long span
            long_span = cols[0].find("span", class_="CellPlayerName--long")
            if long_span:
                player = long_span.get_text(strip=True)
            else:
                # Fallback to heuristic cleaning
                player = _clean_player_name(cols[0].get_text(strip=True))

            position = cols[1].get_text(strip=True)
            date_updated = cols[2].get_text(strip=True)
            injury = cols[3].get_text(strip=True)
            status = cols[4].get_text(strip=True)
            data.append({
                "team": team_full,
                "player": player,
                "position": position,
                "date": date_updated,
                "injury": injury,
                "status": status,
                "scrape_time": now,
            })

    return pd.DataFrame(data)

def save_injury_data(df, filename="nba_injuries.csv"):
    from datetime import datetime
    timestamp = datetime.now().isoformat()
    with open(filename, "w") as f:
        f.write(f"# timestamp: {timestamp}\n")
        df.to_csv(f, index=False)

def main():
    df = fetch_injury_data()
    save_injury_data(df)
    print(f"Saved injury data to nba_injuries.csv with {len(df)} records.")

if __name__ == "__main__":
    main()
