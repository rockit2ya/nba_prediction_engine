import pandas as pd
from nba_api.live.nba.endpoints import scoreboard
import time

def fetch_nba_scores_api():
    """
    Fetch NBA scores using nba_api live scoreboard
    """
    try:
        sb = scoreboard.ScoreBoard()
        games = sb.get_dict()['scoreboard']['games']
        scores = {}
        for game in games:
            away = game['awayTeam']['teamName']
            home = game['homeTeam']['teamName']
            away_score = int(game['awayTeam']['score'])
            home_score = int(game['homeTeam']['score'])
            status = game['gameStatusText']
            if 'Final' in status:
                scores[(away, home)] = (away_score, home_score)
        return scores
    except Exception as e:
        print(f"[nba_api] NBA score fetch failed: {e}")
        return None

def update_bet_tracker_with_nba_scores(csv_path, scores):
    df = pd.read_csv(csv_path)
    # Ensure Notes column is string/object dtype
    if 'Notes' in df.columns:
        df['Notes'] = df['Notes'].astype(str)
    for idx, row in df.iterrows():
        matchup = (row['Away'], row['Home'])
        if matchup in scores:
            away_score, home_score = scores[matchup]
            pick = row['Pick']
            result = 'WIN' if (pick == row['Home'] and home_score > away_score) or (pick == row['Away'] and away_score > home_score) else 'LOSS'
            df.at[idx, 'Result'] = result
            df.at[idx, 'Notes'] = f"Final Score: {row['Away']} {away_score} - {row['Home']} {home_score}"
    df.to_csv(csv_path, index=False)
    print(f"[✓] Bet tracker updated with NBA scores.")

def main():
    csv_path = "bet_tracker_2026-02-09.csv"
    scores = fetch_nba_scores_api()
    if scores:
        update_bet_tracker_with_nba_scores(csv_path, scores)
    else:
        print("[!] No NBA scores available from nba_api.")

if __name__ == "__main__":
    main()
