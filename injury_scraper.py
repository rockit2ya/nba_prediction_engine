import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime

# URL for NBA injury report
INJURY_URL = "https://www.cbssports.com/nba/injuries/"

def fetch_injury_data(url=INJURY_URL):
    response = requests.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    injury_table = soup.find("table", {"class": "TableBase-table"})
    if not injury_table:
        raise ValueError("Injury table not found on page.")
    rows = injury_table.find_all("tr")[1:]  # Skip header
    data = []
    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 5:
            continue
        team = cols[0].text.strip()
        player = cols[1].text.strip()
        position = cols[2].text.strip()
        injury = cols[3].text.strip()
        status = cols[4].text.strip()
        data.append({
            "team": team,
            "player": player,
            "position": position,
            "injury": injury,
            "status": status,
            "scrape_time": datetime.now().isoformat()
        })
    return pd.DataFrame(data)

def save_injury_data(df, filename="nba_injuries.csv"):
    df.to_csv(filename, index=False)

def main():
    df = fetch_injury_data()
    save_injury_data(df)
    print(f"Saved injury data to nba_injuries.csv with {len(df)} records.")

if __name__ == "__main__":
    main()
