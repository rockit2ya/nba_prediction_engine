# NBA News Cache Generator
# Run this script to fetch and cache NBA news for offline use


import feedparser
import json
import signal

NEWS_FEED_URLS = [
    'https://www.espn.com/espn/rss/nba/news'
]

news_items = []

class TimeoutException(Exception):
    pass

def handler(signum, frame):
    raise TimeoutException()

# Set timeout (seconds)
TIMEOUT = 20
signal.signal(signal.SIGALRM, handler)
signal.alarm(TIMEOUT)

try:
    for url in NEWS_FEED_URLS:
        try:
            d = feedparser.parse(url)
            for entry in d.entries:
                news_items.append({
                    'title': entry.title,
                    'summary': entry.summary,
                    'published': entry.published
                })
        except Exception as e:
            print(f"[!] Error fetching {url}: {e}")
except TimeoutException:
    print(f"[!] News fetch timed out after {TIMEOUT} seconds.")
except Exception as e:
    print(f"[!] Unexpected error: {e}")
finally:
    signal.alarm(0)
    # Always write cache file, even if empty
    if not news_items:
        news_items = [{
            'title': 'No NBA news available',
            'summary': 'No news could be fetched or no significant news today.',
            'published': ''
        }]
    from datetime import datetime
    news_cache = {
        "timestamp": datetime.now().isoformat(),
        "data": news_items
    }
    with open('nba_news_cache.json', 'w') as f:
        json.dump(news_cache, f, indent=2)
    print(f"[✓] Cached {len(news_items)} NBA news items to nba_news_cache.json.")
