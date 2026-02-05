import pandas as pd
from datetime import datetime
from nba_api.stats.endpoints import scoreboardv2
from nba_api.stats.static import teams
from nba_analytics import predict_nba_spread

def get_team_mapping():
    """Creates a lookup dictionary for ID -> Full Name."""
    nba_teams = teams.get_teams()
    return {team['id']: team['full_name'] for team in nba_teams}

def display_dynamic_schedule():
    """Pulls today's NBA games and displays them with pretty formatting."""
    print("\n" + "="*75)
    print(f"--- 🏀 NBA DYNAMIC SCOREBOARD | {datetime.today().strftime('%B %d, %Y')} ---")
    print("="*75)
    
    # Initialize lookup and fetch scoreboard
    team_lookup = get_team_mapping()
    board = scoreboardv2.ScoreboardV2()
    games_df = board.get_data_frames()[0]
    
    if games_df.empty:
        print("📭 No games scheduled for today.")
        return {}

    dynamic_schedule = {}
    
    # Header for the table
    print(f"{'ID':<5} {'AWAY TEAM':<25} {'HOME TEAM':<25} {'TIME (EST)':<15}")
    print("-" * 75)

    for i, row in games_df.iterrows():
        gid = f"G{i+1}"
        # Map IDs to Full Names
        away_name = team_lookup.get(row['VISITOR_TEAM_ID'], "Unknown Team")
        home_name = team_lookup.get(row['HOME_TEAM_ID'], "Unknown Team")
        time = row['GAME_STATUS_TEXT'].strip()
        
        # Store for the selection loop
        dynamic_schedule[gid] = (away_name, home_name, time)
        
        # Pretty print the row
        print(f"{gid:<5} {away_name:<25} {home_name:<25} {time:<15}")
        
    return dynamic_schedule

def run_ui():
    schedule = display_dynamic_schedule()
    if not schedule: return

    while True:
        print("\n" + "—" * 50)
        choice = input("Select a Game ID to analyze (or 'Q' to quit): ").upper()
        
        if choice == 'Q':
            print("\nShutting down. Good luck with your bets, Johnny!")
            break
            
        if choice in schedule:
            away_team, home_team, time = schedule[choice]
            print(f"\n[ANALYZING] {away_team} at {home_team} ({time})")
            
            try:
                market_line = float(input(f"Enter Market Spread for {home_team} (e.g. -3.5): "))
                
                # Fetch prediction from analytics engine
                model_line = predict_nba_spread(away_team, home_team)
                edge = round(abs(model_line - market_line), 2)

                print("\n" + "•" * 45)
                print(f"ENGINE FAIR LINE:   {model_line}")
                print(f"MARKET LINE:        {market_line}")
                print(f"CALCULATED EDGE:    {edge} points")
                print("•" * 45)

                if edge >= 2.5:
                    side = home_team if model_line < market_line else away_team
                    print(f"🔥 MASSIVE SIGNAL: Bet on {side}")
                elif edge >= 1.0:
                    print("🟢 MODERATE SIGNAL: Small value identified.")
                else:
                    print("⚪ NO SIGNAL: Market is currently efficient.")
                    
            except ValueError:
                print("⚠️ Error: Please enter a numeric spread.")
            except Exception as e:
                print(f"⚠️ Analytics Error: {e}")
        else:
            print(f"⚠️ '{choice}' is not a valid Game ID.")

if __name__ == "__main__":
    run_ui()
