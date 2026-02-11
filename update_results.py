#!/usr/bin/env python3
"""
update_results.py — Fetches final scores from NBA API and updates bet tracker CSVs.

Usage:
    python update_results.py

Presents a menu of available bet_tracker_*.csv files, fetches completed game
results from the NBA API, and updates the Result and Notes columns automatically.
"""

import os
import glob
import re
import pandas as pd
from datetime import datetime
from nba_api.stats.endpoints import scoreboardv2
from nba_api.stats.static import teams as nba_teams
import time

# ─── Team Name Mapping ───────────────────────────────────────────────────────
# Build a lookup: nickname (e.g., "Mavericks") -> full team info
ALL_TEAMS = nba_teams.get_teams()
NICKNAME_MAP = {t['nickname']: t for t in ALL_TEAMS}

# Common alternate names the CSV might use vs what the API returns
NICKNAME_ALIASES = {
    'Blazers': 'Trail Blazers',
    'Sixers': '76ers',
    'Wolves': 'Timberwolves',
}


def resolve_nickname(name):
    """Resolve a team nickname to the canonical NBA API nickname."""
    name = name.strip()
    if name in NICKNAME_MAP:
        return name
    if name in NICKNAME_ALIASES:
        return NICKNAME_ALIASES[name]
    # Fuzzy fallback: check if name is a substring of any nickname
    for nick in NICKNAME_MAP:
        if name.lower() in nick.lower() or nick.lower() in name.lower():
            return nick
    return name


def find_bet_tracker_files():
    """Find all bet_tracker_*.csv files in the project directory."""
    pattern = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bet_tracker_*.csv')
    files = sorted(glob.glob(pattern), reverse=True)
    return files


def fetch_scores_for_date(date_str):
    """
    Fetch all final game scores for a given date (YYYY-MM-DD) from the NBA API.
    Returns a list of dicts: {away_name, home_name, away_score, home_score, status}
    """
    dt = datetime.strptime(date_str, '%Y-%m-%d')
    api_date = dt.strftime('%m/%d/%Y')

    print(f"  Fetching scores from NBA API for {date_str}...")
    try:
        sb = scoreboardv2.ScoreboardV2(game_date=api_date)
        time.sleep(0.6)  # Rate limit courtesy
    except Exception as e:
        print(f"  ❌ NBA API Error: {e}")
        return []

    # Parse GameHeader for game IDs and status
    game_header = sb.game_header.get_data_frame()
    line_score = sb.line_score.get_data_frame()

    results = []
    for _, game in game_header.iterrows():
        game_id = game['GAME_ID']
        status = game['GAME_STATUS_ID']  # 1=Scheduled, 2=In Progress, 3=Final

        # Get the two teams from line_score for this game
        game_lines = line_score[line_score['GAME_ID'] == game_id].sort_values('TEAM_ID')

        if len(game_lines) < 2:
            continue

        # The away team is listed first in the matchup (VISITOR @ HOME)
        # NBA API GAME_HEADER has HOME_TEAM_ID and VISITOR_TEAM_ID
        home_id = game['HOME_TEAM_ID']
        visitor_id = game['VISITOR_TEAM_ID']

        home_line = game_lines[game_lines['TEAM_ID'] == home_id]
        away_line = game_lines[game_lines['TEAM_ID'] == visitor_id]

        if home_line.empty or away_line.empty:
            continue

        home_row = home_line.iloc[0]
        away_row = away_line.iloc[0]

        results.append({
            'away_name': away_row['TEAM_NICKNAME'] if 'TEAM_NICKNAME' in away_row else away_row.get('TEAM_NAME', ''),
            'home_name': home_row['TEAM_NICKNAME'] if 'TEAM_NICKNAME' in home_row else home_row.get('TEAM_NAME', ''),
            'away_abbrev': away_row.get('TEAM_ABBREVIATION', ''),
            'home_abbrev': home_row.get('TEAM_ABBREVIATION', ''),
            'away_score': int(away_row['PTS']) if pd.notna(away_row['PTS']) else None,
            'home_score': int(home_row['PTS']) if pd.notna(home_row['PTS']) else None,
            'status': int(status),  # 3 = Final
        })

    return results


def match_game(row, scores):
    """
    Match a bet tracker row to an API game result by team nicknames.
    Returns the matching score dict or None.
    """
    away_csv = resolve_nickname(row['Away'])
    home_csv = resolve_nickname(row['Home'])

    for s in scores:
        # Try matching by nickname
        away_api = s['away_name']
        home_api = s['home_name']

        away_match = (away_csv.lower() == away_api.lower() or
                      away_csv.lower() in away_api.lower() or
                      away_api.lower() in away_csv.lower())
        home_match = (home_csv.lower() == home_api.lower() or
                      home_csv.lower() in home_api.lower() or
                      home_api.lower() in home_csv.lower())

        if away_match and home_match:
            return s

    return None


def determine_result(row, score):
    """
    Determine WIN or LOSS based on the Pick column and final scores.
    Positive spread = pick won by that margin, negative = lost.
    """
    pick = row['Pick'].strip()
    away_name = row['Away'].strip()
    home_name = row['Home'].strip()

    away_score = score['away_score']
    home_score = score['home_score']

    if away_score is None or home_score is None:
        return 'PENDING', ''

    # Determine if the pick won the game outright (moneyline-style for spread bets)
    # The pick in these CSVs is the side the model recommends
    # We check: did the picked side cover the market spread?
    pick_resolved = resolve_nickname(pick)
    away_resolved = resolve_nickname(away_name)
    home_resolved = resolve_nickname(home_name)

    # Figure out if pick is home or away
    if pick_resolved.lower() == home_resolved.lower():
        # Pick is the home team
        # Market spread is from the home perspective (negative = home favored)
        actual_margin = home_score - away_score  # positive = home won
        market = float(row['Market'])
        # Home covers if actual_margin > -market (market is from home perspective)
        # e.g., Market = -8.5 means home favored by 8.5; home covers if margin > 8.5
        # e.g., Market = 3.5 means home is underdog by 3.5; home covers if margin > -3.5
        covered = actual_margin > (-market)
    elif pick_resolved.lower() == away_resolved.lower():
        # Pick is the away team
        actual_margin = away_score - home_score  # positive = away won
        market = float(row['Market'])
        # Market is from home perspective, so away covers if away_margin > market
        # e.g., Market = -8.5 (home favored), away covers if away_margin > -8.5
        # e.g., Market = 9.5 (away favored), away covers if away_margin > 9.5
        covered = actual_margin > market
    else:
        # Can't match pick to either team — fallback to simple W/L
        covered = False

    final_score = f"Final Score: {row['Away']} {away_score} - {row['Home']} {home_score}"
    result = 'WIN' if covered else 'LOSS'
    return result, final_score


def update_tracker(filepath):
    """Main logic: load CSV, fetch scores, update results, save."""
    # Extract date from filename
    match = re.search(r'bet_tracker_(\d{4}-\d{2}-\d{2})\.csv', filepath)
    if not match:
        print("❌ Could not parse date from filename.")
        return
    date_str = match.group(1)

    df = pd.read_csv(filepath)

    # Check how many are pending
    pending_mask = df['Result'].str.upper().str.strip() == 'PENDING'
    pending_count = pending_mask.sum()

    if pending_count == 0:
        print("  ✅ No pending games — all results already entered.")
        print(f"\n  Current results:")
        for _, row in df.iterrows():
            print(f"    {row['ID']}: {row['Away']} @ {row['Home']} → {row['Result']}  {row.get('Notes', '')}")
        return

    print(f"  Found {pending_count} pending game(s) to update.\n")

    # Fetch scores from API
    scores = fetch_scores_for_date(date_str)

    if not scores:
        print("  ⚠️  No game data returned from NBA API.")
        print("     Games may not have started yet, or the API may be unavailable.")
        return

    print(f"  Retrieved {len(scores)} game(s) from API.\n")

    updated = 0
    still_pending = 0

    for idx, row in df.iterrows():
        if str(row['Result']).strip().upper() != 'PENDING':
            continue

        score = match_game(row, scores)

        if score is None:
            print(f"  ⚠️  {row['ID']}: {row['Away']} @ {row['Home']} — No matching game found in API")
            still_pending += 1
            continue

        if score['status'] != 3:
            status_text = {1: 'Not Started', 2: 'In Progress'}.get(score['status'], f'Status {score["status"]}')
            print(f"  ⏳ {row['ID']}: {row['Away']} @ {row['Home']} — Game {status_text}")
            still_pending += 1
            continue

        result, final_score = determine_result(row, score)
        df.at[idx, 'Result'] = result
        df.at[idx, 'Notes'] = final_score

        icon = '✅' if result == 'WIN' else '❌'
        print(f"  {icon} {row['ID']}: {row['Away']} @ {row['Home']} → {result}  ({final_score})")
        updated += 1

    # Save updated CSV
    df.to_csv(filepath, index=False)

    print(f"\n  Summary: {updated} updated, {still_pending} still pending")
    print(f"  💾 Saved to {os.path.basename(filepath)}")


def main():
    print("\n" + "=" * 60)
    print("  📊 NBA Bet Tracker — Result Updater")
    print("=" * 60)

    files = find_bet_tracker_files()
    if not files:
        print("\n  ❌ No bet_tracker_*.csv files found.")
        return

    print("\n  Available bet tracker files:\n")
    for i, f in enumerate(files, 1):
        basename = os.path.basename(f)
        df = pd.read_csv(f)
        pending = (df['Result'].str.upper().str.strip() == 'PENDING').sum()
        total = len(df)
        status = f"{pending} pending" if pending > 0 else "all complete"
        print(f"    [{i}] {basename}  ({total} games, {status})")

    print(f"    [A] Update ALL files with pending games")
    print(f"    [Q] Quit\n")

    choice = input("  Select: ").strip().upper()

    if choice == 'Q':
        return

    if choice == 'A':
        for f in files:
            df = pd.read_csv(f)
            pending = (df['Result'].str.upper().str.strip() == 'PENDING').sum()
            if pending > 0:
                print(f"\n{'─' * 60}")
                print(f"  Updating {os.path.basename(f)}...")
                update_tracker(f)
        print(f"\n{'─' * 60}")
        print("  ✅ All files processed.")
        return

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(files):
            print(f"\n{'─' * 60}")
            print(f"  Updating {os.path.basename(files[idx])}...")
            update_tracker(files[idx])
        else:
            print("  ❌ Invalid selection.")
    except ValueError:
        print("  ❌ Invalid input.")


if __name__ == "__main__":
    main()
