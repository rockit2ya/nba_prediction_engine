import pandas as pd
from nba_api.stats.endpoints import leaguedashteamstats

def standardize_team_name(name):
    """
    Normalizes team names and abbreviations to match official NBA API strings.
    """
    # Dictionary mapping common shorthand/aliases to official API names
    mapping = {
        # CRITICAL: API Mismatches 
        "Los Angeles Clippers": "LA Clippers",
        "Philly 76ers": "Philadelphia 76ers",
        "Portland Trailblazers": "Portland Trail Blazers"
    }
    
    # Check if the name exists in our map; if not, return the original name
    return mapping.get(name, name)

def get_team_four_factors(season='2025-26', last_n_games=10):
    try:
        stats = leaguedashteamstats.LeagueDashTeamStats(
            season=season,
            last_n_games=last_n_games,
            measure_type_detailed_defense='Four Factors'
        ).get_data_frames()[0]
        
        if stats.empty:
            return pd.DataFrame()

        columns = [
            'TEAM_ID', 'TEAM_NAME', 'EFG_PCT', 'TM_TOV_PCT', 
            'OREB_PCT', 'FTA_RATE', 'OPP_EFG_PCT', 
            'OPP_TM_TOV_PCT', 'OPP_OREB_PCT', 'OPP_FTA_RATE'
        ]
        return stats[columns]
    except Exception:
        return pd.DataFrame()

def calculate_pace_and_ratings(season='2025-26', last_n_games=10):
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
    # 📝 Standardize names immediately upon input
    away_team = standardize_team_name(away_team)
    home_team = standardize_team_name(home_team)
    
    ratings = calculate_pace_and_ratings()
    
    if ratings.empty:
        raise Exception("NBA API returned an empty dataset. Try again in 60s.")

    # Search using standardized names
    home_rows = ratings[ratings['TEAM_NAME'] == home_team]
    away_rows = ratings[ratings['TEAM_NAME'] == away_team]

    if home_rows.empty or away_rows.empty:
        missing = home_team if home_rows.empty else away_team
        raise Exception(f"Stat lookup failed for {missing}. (Standardized: {missing})")

    home_data = home_rows.iloc[0]
    away_data = away_rows.iloc[0]

    # Analytics Math
    raw_diff = (home_data['OFF_RATING'] - away_data['DEF_RATING']) - \
               (away_data['OFF_RATING'] - home_data['DEF_RATING'])
    
    avg_pace = (home_data['PACE'] + away_data['PACE']) / 2
    projected_spread = (raw_diff * (avg_pace / 100)) + 3.0 # Home Court Advantage
    
    return round(projected_spread, 2)
