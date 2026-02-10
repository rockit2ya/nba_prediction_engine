import os
import subprocess
import time
from datetime import datetime
from nba_api.live.nba.endpoints import scoreboard
from nba_api.stats.static import teams
from nba_analytics import predict_nba_spread, log_bet, get_cache_times, calculate_pace_and_ratings

def calculate_kelly(market, fair_line):
    """Conservative Quarter-Kelly Criterion bankroll management."""
    b, edge = 0.91, abs(fair_line - market)
    prob = min(0.70, max(0.48, 0.524 + (edge * 0.015)))
    kelly_f = ((b * prob) - (1 - prob)) / b
    return round(max(0, kelly_f * 0.25) * 100, 2)

def run_ui():
    today_display = datetime.now().strftime("%B %d, %Y")

    # Pre-load analytics data/cache
    print("\n[SYSTEM] Initializing Pro Analytics Engine...")
    calculate_pace_and_ratings()

    from nba_analytics import get_cache_times

    try:
        while True:
            cache_times = get_cache_times()
            print("\n" + "="*75)
            print(f"--- 🏀 NBA PRO ENGINE (V3) | {today_display} ---")
            print("--- DATA CACHE FRESHNESS ---")
            print(f"  Team Stats:   {cache_times.get('stats', 'Unknown')}")
            print(f"  Injuries:     {cache_times.get('injuries', 'Unknown')}")
            print(f"  News:         {cache_times.get('news', 'Unknown')}")
            print(f"  Rest Penalty: {cache_times.get('rest', 'Unknown')}")
            print("="*75)

            schedule = {}
            try:
                sb = scoreboard.ScoreBoard()
                games = sb.get_dict()['scoreboard']['games']

                for i, game in enumerate(games):
                    gid = f"G{i+1}"
                    away = game['awayTeam']['teamName']
                    home = game['homeTeam']['teamName']
                    status = game['gameStatusText']
                    schedule[gid] = (away, home)
                    print(f"{gid:<4} {away:<20} @ {home:<20} {status}")
            except Exception:
                print("❌ Scoreboard Error: Unable to reach NBA Stats Server.")
                print("💡 TIP: Type 'C' to analyze a Custom Matchup manually.")

            print("-" * 75)
            print("COMMANDS: [G#] (Analyze) | [R] (Refresh Data) | [C] (Custom) | [Q] (Quit)")
            choice = input("Enter Command: ").upper()

            if choice == 'Q':
                print("Shutting down. Good luck tonight, Johnny!")
                break

            elif choice == 'R':
                print("\n🔄 Refreshing all NBA data (stats, injuries, news, rest)...")
                script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fetch_all_nba_data.sh')
                result = subprocess.run(['bash', script_path], capture_output=True, text=True)
                # Show summary lines to the user
                output = result.stdout + result.stderr
                for line in output.splitlines():
                    if any(tag in line for tag in ['[SUCCESS]', '[ERROR]', '[SUMMARY]', '[COMPLETE]', '[FATAL]', '  -']):
                        print(line)
                if result.returncode != 0:
                    print("[ERROR] Data refresh failed. Check fetch_all_nba_data.log for details.")
                else:
                    # Reload caches in-memory
                    calculate_pace_and_ratings(force_refresh=True)
                    print("[✓] All caches reloaded.")
                continue

            elif choice in schedule or choice == 'C':
                if choice == 'C':
                    away = input("Enter Away Team Name: ")
                    home = input("Enter Home Team Name: ")
                else:
                    away, home = schedule[choice]

                print(f"\n[ANALYZING] {away} vs {home}...")

                try:
                    line_in = input(f"Market Line for {home} (e.g., -5.5): ")
                    market = float(line_in)


                    # Pro Logic: Injury Star Tax + Fatigue + HCA + late-breaking flag
                    fair_line, q_players, news, flag = predict_nba_spread(away, home)
                    edge = round(abs(fair_line - market), 2)
                    kelly = calculate_kelly(market, fair_line)

                    # Confidence Grade Logic
                    conf = "HIGH"
                    if len(q_players) >= 2: conf = "LOW (High Injury Volatility)"
                    elif len(q_players) == 1: conf = "MEDIUM"

                    print("\n" + "•"*45)
                    print(f"PRO ENGINE LINE: {fair_line}")
                    print(f"MARKET SPREAD:   {market}")
                    print(f"CALCULATED EDGE: {edge} pts")
                    print(f"KELLY SUGGESTION: Risk {kelly}% of Bankroll")
                    print(f"MODEL CONFIDENCE: {conf}")
                    print("•"*45)

                    if q_players:
                        print(f"⚠️  GTD/QUESTIONABLE: {', '.join(q_players)}")
                    if flag:
                        print(f"🚨 ALERT: Late-breaking lineup/injury news detected! Double-check before betting.")

                    recommendation = home if fair_line < market else away
                    if edge >= 5 and "HIGH" in conf:
                        print(f"🔥 STRONG SIGNAL: Bet on {recommendation}")
                    elif edge > 11:
                        print(f"🚨 EXTREME EDGE ALERT: Check for late-breaking scratches!")

                    # Log to date-stamped CSV
                    log_bet(choice, away, home, fair_line, market, edge, recommendation, kelly)

                    print(f"\n[SUCCESS] Analysis logged. Returning to Scoreboard...")

                except Exception as e:
                    print(f"❌ Error during analysis: {e}")
                    time.sleep(3)
            else:
                print("❌ Command not recognized.")
    except KeyboardInterrupt:
        print("\n[EXIT] Keyboard interrupt received. Shutting down gracefully. Good luck tonight, Johnny!")

if __name__ == "__main__":
    run_ui()
