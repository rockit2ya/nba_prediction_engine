import pandas as pd
from nba_api.stats.endpoints import leaguedashteamstats

def standardize_team_name(name):
    """Normalizes names for known API inconsistencies."""
    mapping = {
        "Los Angeles Clippers": "LA Clippers",
        "Portland Trailblazers": "Portland Trail Blazers",
    }
    return mapping.get(name, name)

def calculate_pace_and_ratings(season='2025-26', last_n_games=10):
    """Fetches Pace and Ratings with error handling."""
    try:
        adv_stats = leaguedashteamstats.LeagueDashTeamStats(
            season=season,
            last_n_games=last_n_games,
            measure_type_detailed_defense='Advanced'
        ).get_data_frames()[0]
        
        if adv_stats.empty:
            return pd.DataFrame()
            
        return adv_stats[['TEAM_NAME', 'OFF_RATING', 'DEF_RATING', 'PACE']]
    except Exception:
        return pd.DataFrame()

def predict_nba_spread(away_team, home_team):
    """Predicts spread with Auto-Mismatch Detection."""
    # 1. Standardize names immediately
    away_std = standardize_team_name(away_team)
    home_std = standardize_team_name(home_team)
    
    # 2. Fetch the data (This is the function that was 'missing')
    ratings = calculate_pace_and_ratings()
    
    if ratings.empty:
        raise Exception("NBA API returned an empty dataset. Try again in 60s.")

    # 3. AUTO-MISMATCH DETECTION
    all_api_names = ratings['TEAM_NAME'].unique()
    
    for team in [away_std, home_std]:
        if team not in all_api_names:
            print(f"\n⚠️  [NAME MISMATCH DETECTED]")
            print(f"Engine tried to find: '{team}'")
            print(f"Top 3 API examples: {list(all_api_names[:3])}")
            raise Exception(f"Stat lookup failed for '{team}'.")

    # 4. Calculation Logic
    home_data = ratings[ratings['TEAM_NAME'] == home_std].iloc[0]
    away_data = ratings[ratings['TEAM_NAME'] == away_std].iloc[0]

    raw_diff = (home_data['OFF_RATING'] - away_data['DEF_RATING']) - \
               (away_data['OFF_RATING'] - home_data['DEF_RATING'])
    
    avg_pace = (home_data['PACE'] + away_data['PACE']) / 2
    projected_spread = (raw_diff * (avg_pace / 100)) + 3.0 # Home Court
    
    return round(projected_spread, 2)
