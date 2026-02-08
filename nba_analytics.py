import pandas as pd
from nba_api.stats.endpoints import leaguedashteamstats

def standardize_team_name(name):
    """
    Standardizes names for known API inconsistencies.
    """
    mapping = {
        "Los Angeles Clippers": "LA Clippers",
        "Portland Trailblazers": "Portland Trail Blazers",
    }
    return mapping.get(name, name)

def predict_nba_spread(away_team, home_team):
    # 📝 Standardize names immediately
    away_std = standardize_team_name(away_team)
    home_std = standardize_team_name(home_team)
    
    ratings = calculate_pace_and_ratings()
    
    if ratings.empty:
        raise Exception("NBA API returned an empty dataset. Try again in 60s.")

    # 🕵️ NEW: AUTO-MISMATCH DETECTION
    all_api_names = ratings['TEAM_NAME'].unique()
    
    for team in [away_std, home_std]:
        if team not in all_api_names:
            # Check if it's a "Close Match" to help the user
            print(f"\n⚠️  [NAME MISMATCH DETECTED]")
            print(f"Engine tried to find: '{team}'")
            print(f"Official API list contains {len(all_api_names)} teams.")
            print(f"Top 3 similar names in API: {all_api_names[:3]}...")
            raise Exception(f"Stat lookup failed for '{team}'. Update your mapping dictionary.")

    # Normal logic continues if names are found
    home_data = ratings[ratings['TEAM_NAME'] == home_std].iloc[0]
    away_data = ratings[ratings['TEAM_NAME'] == away_std].iloc[0]

    # Analytics Math
    raw_diff = (home_data['OFF_RATING'] - away_data['DEF_RATING']) - \
               (away_data['OFF_RATING'] - home_data['DEF_RATING'])
    
    avg_pace = (home_data['PACE'] + away_data['PACE']) / 2
    projected_spread = (raw_diff * (avg_pace / 100)) + 3.0
    
    return round(projected_spread, 2)
