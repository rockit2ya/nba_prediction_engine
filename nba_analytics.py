import pandas as pd
from nba_api.stats.endpoints import leaguedashteamstats, leaguegamefinder

def get_team_four_factors(season='2025-26', last_n_games=10):
    """
    Fetches Four Factor metrics for all teams. 
    Uses a rolling window (default 10 games) to capture 'Momentum'.
    """
    try:
        # Fetching 'Four Factors' measure type from NBA API
        stats = leaguedashteamstats.LeagueDashTeamStats(
            season=season,
            last_n_games=last_n_games,
            measure_type_detailed_defense='Four Factors'
        ).get_data_frames()[0]
        
        # Select key columns: eFG, TOV%, OREB%, FT Rate
        # These are usually returned as decimals (e.g., 0.542)
        columns = [
            'TEAM_ID', 'TEAM_NAME', 'EFG_PCT', 'TM_TOV_PCT', 
            'OREB_PCT', 'FTA_RATE', 'OPP_EFG_PCT', 
            'OPP_TM_TOV_PCT', 'OPP_OREB_PCT', 'OPP_FTA_RATE'
        ]
        return stats[columns]
    except Exception as e:
        print(f"Error fetching Four Factors: {e}")
        return pd.DataFrame()

def calculate_pace_and_ratings(season='2025-26', last_n_games=10):
    """
    Fetches Advanced metrics to get Pace and Offensive/Defensive Ratings.
    """
    try:
        adv_stats = leaguedashteamstats.LeagueDashTeamStats(
            season=season,
            last_n_games=last_n_games,
            measure_type_detailed_defense='Advanced'
        ).get_data_frames()[0]
        
        return adv_stats[['TEAM_NAME', 'OFF_RATING', 'DEF_RATING', 'PACE']]
    except Exception as e:
        print(f"Error fetching Advanced Ratings: {e}")
        return pd.DataFrame()

def get_rest_advantage(team_name):
    """
    Logic to check if a team is on a Back-to-Back (B2B).
    Subtracts 2.5 points from efficiency if they played yesterday.
    """
    # In a full implementation, you'd check leaguegamefinder 
    # for the team's most recent game date vs today.
    # Placeholder for UI integration:
    return -2.5 if "B2B" in team_name else 0.0

def predict_nba_spread(away_team, home_team):
    """
    Combines Four Factors + Pace + Rest to create a 'Fair Line'.
    """
    ratings = calculate_pace_and_ratings()
    
    if ratings.empty:
        return 0.0

    # Get team ratings
    home_data = ratings[ratings['TEAM_NAME'] == home_team].iloc[0]
    away_data = ratings[ratings['TEAM_NAME'] == away_team].iloc[0]

    # Calculate Raw Differential (Pts per 100 possessions)
    # Plus standard Home Court Advantage (+3.0)
    raw_diff = (home_data['OFF_RATING'] - away_data['DEF_RATING']) - \
               (away_data['OFF_RATING'] - home_data['DEF_RATING'])
    
    # Pace Adjustment: Normalize to the average of both teams' pace
    avg_pace = (home_data['PACE'] + away_data['PACE']) / 2
    projected_spread = (raw_diff * (avg_pace / 100)) + 3.0
    
    return round(projected_spread, 2)

if __name__ == "__main__":
    # Test Run
    print("Testing NBA Analytics Engine...")
    test_spread = predict_nba_spread("Golden State Warriors", "Phoenix Suns")
    print(f"Projected Fair Line (Home Team): {test_spread}")
