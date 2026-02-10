import requests
from bs4 import BeautifulSoup
import feedparser

def fetch_nba_lineups_espn():
    """Scrape ESPN for NBA lineups and injury reports."""
    url = "https://www.espn.com/nba/injuries"
    try:
        res = requests.get(url, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        teams = {}
        for table in soup.find_all('table', class_='Table'):
            team_name = table.find_previous('h2').text.strip()
            players = []
            for row in table.find_all('tr')[1:]:
                cols = row.find_all('td')
                if len(cols) >= 4:
                    player = cols[0].text.strip()
                    injury = cols[1].text.strip()
                    status = cols[2].text.strip()
                    return_date = cols[3].text.strip()
                    players.append({'player': player, 'injury': injury, 'status': status, 'return': return_date})
            teams[team_name] = players
        return teams
    except Exception as e:
        print(f"[Lineup Scraper] ESPN error: {e}")
        return {}

def fetch_nba_news_rss():
    """Fetch NBA news from ESPN RSS feed for late scratches and breaking news."""
    feed_url = "https://www.espn.com/espn/rss/nba/news"
    try:
        d = feedparser.parse(feed_url)
        news = []
        for entry in d.entries:
            news.append({'title': entry.title, 'summary': entry.summary, 'published': entry.published})
        return news
    except Exception as e:
        print(f"[NBA News RSS] Error: {e}")
        return []

if __name__ == "__main__":
    print("--- ESPN NBA Lineups/Injuries ---")
    lineups = fetch_nba_lineups_espn()
    for team, players in lineups.items():
        print(f"{team}:")
        for p in players:
            print(f"  {p['player']} | {p['injury']} | {p['status']} | {p['return']}")
    print("\n--- ESPN NBA News RSS ---")
    news = fetch_nba_news_rss()
    for n in news[:10]:
        print(f"{n['published']} | {n['title']}")
