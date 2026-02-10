#!/usr/bin/env python3
"""
Check for late scratches and breaking injury news for tonight's games
Searches multiple news sources with short timeouts
"""
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta

def check_nba_news(timeout=3):
    """Check NBA.com news for late scratch info"""
    try:
        url = "https://www.nba.com"
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
        response = requests.get(url, headers=headers, timeout=timeout)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Look for injury/status announcements
        news_items = []
        # NBA structure changes, look for any injury-related text
        text_content = soup.get_text()
        
        # Simple pattern matching for "out", "scratch", "injury" announcements
        if re.search(r'(out|scratch|injury|unavailable)\s+(today|tonight|game)', text_content, re.IGNORECASE):
            return True  # Found something, flag for review
        return False
    except:
        return False

def check_espn_headlines(timeout=3):
    """Check ESPN NBA headlines for injury news"""
    try:
        url = "https://www.espn.com/nba"
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
        response = requests.get(url, headers=headers, timeout=timeout)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Look for headlines containing injury keywords
        headlines = soup.find_all('a', {'data-testid': 'Link'})
        
        urgent_injuries = []
        for headline in headlines[:20]:  # Check first 20 headlines only
            text = headline.get_text().lower()
            if any(word in text for word in ['out', 'scratch', 'injury', 'ruled out', 'game-time']):
                urgent_injuries.append(headline.get_text())
        
        return urgent_injuries if urgent_injuries else None
    except:
        return None

def check_twitter_nba_alerts(timeout=2):
    """Note: Twitter API requires authentication now, but we can try general search"""
    # This would need Twitter API keys, so we'll note it as unavailable
    return None

def check_for_late_scratches(games_teams):
    """
    Check for late scratches for tonight's games
    games_teams: list of tuples [(away, home), ...]
    Returns: dict of teams with late scratch warnings
    """
    print("🔍 Checking for late scratches...\n")
    
    warnings = {}
    
    # Quick checks with aggressive timeouts
    checks = [
        ("NBA.com", check_nba_news),
        ("ESPN", check_espn_headlines),
    ]
    
    for source_name, check_func in checks:
        try:
            result = check_func()
            if result:
                print(f"⚠️  {source_name}: Found potential injury/scratch alerts")
                if isinstance(result, list):
                    for item in result[:3]:  # Show first 3
                        print(f"   - {item[:60]}...")
                warnings[source_name] = result
        except Exception as e:
            pass  # Silently skip timeouts
    
    if not warnings:
        print("✅ No major scratch alerts found in headlines")
        print("   ℹ️  Always verify team reports before placing high-value bets")
    
    return warnings

def scrape_team_status(team_name, timeout=3):
    """
    Check a specific team's official roster status
    """
    try:
        # Try to fetch team injury report
        url = f"https://www.nba.com/{team_name.lower().replace(' ', '-')}/roster"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=timeout)
        
        if "out" in response.text.lower() or "unavailable" in response.text.lower():
            return True  # Team has reported outages
        return False
    except:
        return False

if __name__ == "__main__":
    # Test with sample games
    sample_games = [
        ("Pistons", "Hornets"),
        ("Thunder", "Lakers"),
        ("76ers", "Trail Blazers"),
    ]
    
    warnings = check_for_late_scratches(sample_games)
    
    print("\n" + "="*60)
    print("MANUAL VERIFICATION CHECKLIST")
    print("="*60)
    print("""
Before placing HIGH-VALUE bets:
[ ] Check team official Twitter/X accounts for latest roster news
[ ] Verify warm-up reports on ESPN/NBA.com 30 mins before tipoff
[ ] Check if star players are present at arena (shootaround)
[ ] Review betting line movements (sharp money may signal scratches)

Recommended timing:
- 1 hour before game: Check official team reports
- 30 mins before: Verify warm-ups (teams post videos)
- 15 mins before: Final confirmation
    """)
