import pandas as pd
import glob
import os

def analyze_bet_tracker(date_str):
    filename = f"bet_tracker_{date_str}.csv"
    if not os.path.exists(filename):
        print(f"File not found: {filename}")
        return
    df = pd.read_csv(filename)
    # Filter high-signal bets (Edge >= 5)
    high_signal = df[df['Edge'] >= 5]
    if high_signal.empty:
        print("No high-signal bets found.")
        return
    # Count win/loss (requires Result column to be updated)
    win = high_signal[high_signal['Result'].str.lower() == 'win']
    loss = high_signal[high_signal['Result'].str.lower() == 'loss']
    pending = high_signal[high_signal['Result'].str.lower() == 'pending']
    print(f"--- Post-Mortem for {filename} ---")
    print(f"Total high-signal bets: {len(high_signal)}")
    print(f"Wins: {len(win)} | Losses: {len(loss)} | Pending: {len(pending)}")
    # Load injury data
    injury_file = "nba_injuries.csv"
    injuries = None
    if os.path.exists(injury_file):
        injuries = pd.read_csv(injury_file)
    else:
        print("Injury file not found, skipping injury analysis.")
    if not loss.empty:
        print("\nLoss Details:")
        loss_patterns = []
        margins = []
        for idx, row in loss.iterrows():
            # Extract margin and final score from Notes if available
            notes = row.get('Notes', '')
            margin = None
            final_score = ''
            import re
            m = re.search(r'Final Score: (\w+) (\d+) - (\w+) (\d+)', str(notes))
            if m:
                away, away_score, home, home_score = m.groups()
                away_score, home_score = int(away_score), int(home_score)
                if row['Pick'] == row['Home']:
                    margin = home_score - away_score
                else:
                    margin = away_score - home_score
                final_score = f"{away} {away_score} - {home} {home_score}"
                margins.append(margin)
            print(f"Game: {row['Away']} @ {row['Home']} | Edge: {row['Edge']} | Pick: {row['Pick']} | Fair: {row['Fair']} | Market: {row['Market']}")
            if final_score:
                print(f"  Final Score: {final_score} | Margin: {margin}")
            # Factor injuries
            injury_reason = False
            if injuries is not None:
                team = row['Pick']
                team_injuries = injuries[injuries['team'].str.contains(team, case=False)]
                if not team_injuries.empty:
                    print("  Injuries impacting pick:")
                    for _, inj_row in team_injuries.iterrows():
                        print(f"    Player: {inj_row['player']} | Position: {inj_row['position']} | Injury: {inj_row['injury']} | Status: {inj_row['status']}")
                        injury_reason = True
                else:
                    print("  No reported injuries for pick team.")
            # Edge check
            edge_reason = float(row['Edge']) < 10
            if edge_reason:
                print("  Edge below 10%: May be too optimistic or not enough signal.")
            loss_patterns.append({
                'game': f"{row['Away']} @ {row['Home']}",
                'injury': injury_reason,
                'low_edge': edge_reason,
                'margin': margin
            })
        # Summarize loss patterns
        print("\nAutomated Loss Pattern Analysis:")
        injury_losses = sum(1 for p in loss_patterns if p['injury'])
        low_edge_losses = sum(1 for p in loss_patterns if p['low_edge'])
        print(f"Losses with injury impact: {injury_losses}")
        print(f"Losses with low edge (<10%): {low_edge_losses}")
        if margins:
            avg_margin = sum(margins) / len(margins)
            print(f"Average margin of defeat: {avg_margin:.2f}")
            print(f"Margins: {margins}")
        if injury_losses == 0 and low_edge_losses == 0:
            print("No common injury or low edge patterns detected. Losses may be due to variance or missing situational factors.")
    # Also summarize win margins
    if not win.empty:
        win_margins = []
        for idx, row in win.iterrows():
            notes = row.get('Notes', '')
            margin = None
            import re
            m = re.search(r'Final Score: (\w+) (\d+) - (\w+) (\d+)', str(notes))
            if m:
                away, away_score, home, home_score = m.groups()
                away_score, home_score = int(away_score), int(home_score)
                if row['Pick'] == row['Home']:
                    margin = home_score - away_score
                else:
                    margin = away_score - home_score
                win_margins.append(margin)
        if win_margins:
            avg_win_margin = sum(win_margins) / len(win_margins)
            print(f"\nAverage margin of victory: {avg_win_margin:.2f}")
            print(f"Win margins: {win_margins}")
    print("\nSummary:")
    if len(high_signal) > 0:
        win_rate = len(win) / len(high_signal)
        avg_edge = high_signal['Edge'].mean()
        print(f"Win Rate: {win_rate:.2%}")
        print(f"Average Edge: {avg_edge:.2f}")
    else:
        print("No high-signal bets to analyze.")

if __name__ == "__main__":
    date_str = input("Enter date (YYYY-MM-DD): ")
    analyze_bet_tracker(date_str)
