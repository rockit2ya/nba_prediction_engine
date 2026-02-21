#!/usr/bin/env python3
"""
update_results.py — Fetches final scores from ESPN and updates bet tracker CSVs.

Usage:
    python update_results.py

Presents a menu of available bet_tracker_*.csv files, fetches completed game
results from the ESPN Scoreboard API, and updates the Result and Notes columns.
"""

import os
import glob
import re
import pandas as pd
import requests
from datetime import datetime
from dotenv import load_dotenv
from nba_teams_static import NICKNAME_MAP, NICKNAME_ALIASES

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

try:
    from odds_api import get_closing_line
    HAS_ODDS_API = True
except ImportError:
    HAS_ODDS_API = False

API_KEY = os.getenv('ODDS_API_KEY', '')

# ─── ESPN Scoreboard API ──────────────────────────────────────────────────────
ESPN_SCOREBOARD_URL = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard'


def resolve_nickname(name):
    """Resolve a team nickname to the canonical NBA API nickname."""
    name = name.strip()
    if name in NICKNAME_MAP:
        return name
    if name in NICKNAME_ALIASES:
        return NICKNAME_ALIASES[name]
    # Exact match against full team names or abbreviations (no substring matching)
    for nick, info in NICKNAME_MAP.items():
        if name.lower() == info['full_name'].lower() or name.lower() == info['abbreviation'].lower():
            return nick
    return name


def find_bet_tracker_files():
    """Find all bet_tracker_*.csv files in the project directory."""
    pattern = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bet_tracker_*.csv')
    files = sorted(glob.glob(pattern), reverse=True)
    return files


def fetch_scores_for_date(date_str):
    """
    Fetch all final game scores for a given date (YYYY-MM-DD) from ESPN.
    Returns a list of dicts: {away_name, home_name, away_score, home_score, status}
    """
    dt = datetime.strptime(date_str, '%Y-%m-%d')
    espn_date = dt.strftime('%Y%m%d')

    print(f"  Fetching scores from ESPN for {date_str}...")
    try:
        resp = requests.get(ESPN_SCOREBOARD_URL, params={'dates': espn_date}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  ❌ ESPN API Error: {e}")
        return []

    events = data.get('events', [])
    results = []

    for event in events:
        status_type = event.get('status', {}).get('type', {})
        status_name = status_type.get('name', '')
        completed = status_type.get('completed', False)

        # Map status to numeric: 1=Scheduled, 2=In Progress, 3=Final
        if completed or status_name == 'STATUS_FINAL':
            status_code = 3
        elif status_name == 'STATUS_IN_PROGRESS':
            status_code = 2
        else:
            status_code = 1

        competitors = event.get('competitions', [{}])[0].get('competitors', [])
        if len(competitors) < 2:
            continue

        away = next((c for c in competitors if c.get('homeAway') == 'away'), None)
        home = next((c for c in competitors if c.get('homeAway') == 'home'), None)
        if not away or not home:
            continue

        away_score = int(away.get('score', 0)) if away.get('score') else None
        home_score = int(home.get('score', 0)) if home.get('score') else None

        results.append({
            'away_name': away['team'].get('shortDisplayName', ''),
            'home_name': home['team'].get('shortDisplayName', ''),
            'away_abbrev': away['team'].get('abbreviation', ''),
            'home_abbrev': home['team'].get('abbreviation', ''),
            'away_score': away_score,
            'home_score': home_score,
            'status': status_code,
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
        # Try matching by nickname (exact match only — no substring)
        away_api = s['away_name']
        home_api = s['home_name']

        away_match = away_csv.lower() == away_api.lower()
        home_match = home_csv.lower() == home_api.lower()

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
        actual_margin = home_score - away_score  # positive = home won
        try:
            market = float(row['Market'])
        except (ValueError, TypeError):
            return 'PENDING', 'Could not parse Market spread'
        # PUSH: exact spread tie
        if actual_margin == (-market):
            final_score = f"Final Score: {row['Away']} {away_score} - {row['Home']} {home_score}"
            return 'PUSH', final_score
        covered = actual_margin > (-market)
    elif pick_resolved.lower() == away_resolved.lower():
        # Pick is the away team
        actual_margin = away_score - home_score  # positive = away won
        try:
            market = float(row['Market'])
        except (ValueError, TypeError):
            return 'PENDING', 'Could not parse Market spread'
        # PUSH: exact spread tie
        if actual_margin == market:
            final_score = f"Final Score: {row['Away']} {away_score} - {row['Home']} {home_score}"
            return 'PUSH', final_score
        covered = actual_margin > market
    else:
        # Can't match pick to either team — return PENDING instead of false LOSS
        final_score = f"Final Score: {row['Away']} {away_score} - {row['Home']} {home_score}"
        return 'PENDING', f"{final_score} (could not match pick '{pick}' to either team)"

    final_score = f"Final Score: {row['Away']} {away_score} - {row['Home']} {home_score}"
    result = 'WIN' if covered else 'LOSS'
    return result, final_score


def calc_payout(result, bet_str, odds_str):
    """
    Calculate payout based on result, bet amount, and American odds.
    WIN:  returns total payout (profit + stake)
    LOSS: returns negative bet amount (lost the stake)
    """
    try:
        bet = float(str(bet_str).replace('$', '').replace(',', '').strip())
        odds = int(str(odds_str).replace('+', '').strip())
    except (ValueError, TypeError):
        return None

    if bet <= 0:
        return None

    if odds == 0:
        return None  # Invalid odds

    if result == 'WIN':
        if odds > 0:
            profit = bet * (odds / 100)
        else:
            profit = bet * (100 / abs(odds))
        return round(profit, 2)  # net profit only
    elif result == 'LOSS':
        return round(-bet, 2)
    elif result == 'PUSH':
        return 0.0  # Push = money returned, no profit/loss
    return None


def update_tracker(filepath):
    """Main logic: load CSV, fetch scores, update results, save."""
    # Extract date from filename
    match = re.search(r'bet_tracker_(\d{4}-\d{2}-\d{2})\.csv', filepath)
    if not match:
        print("❌ Could not parse date from filename.")
        return
    date_str = match.group(1)

    df = pd.read_csv(filepath)

    # Ensure ClosingLine and CLV columns exist
    if 'ClosingLine' not in df.columns:
        df['ClosingLine'] = ''
    if 'CLV' not in df.columns:
        df['CLV'] = ''
    # Ensure PreflightCheck and PreflightNote columns exist
    if 'PreflightCheck' not in df.columns:
        df['PreflightCheck'] = ''
    if 'PreflightNote' not in df.columns:
        df['PreflightNote'] = ''

    # Ensure string columns don't get inferred as float64
    for col in ['Notes', 'Book', 'Odds', 'Bet', 'Payout', 'Timestamp', 'Confidence', 'Type', 'ToWin', 'ClosingLine', 'CLV', 'PreflightCheck', 'PreflightNote']:
        if col in df.columns:
            df[col] = df[col].fillna('').astype(str)

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
        print("  ⚠️  No game data returned from ESPN.")
        print("     Games may not have started yet, or it's an off-day (All-Star break, etc.).")
        return

    print(f"  Retrieved {len(scores)} game(s) from ESPN.\n")

    updated = 0
    still_pending = 0

    # ── Pre-populate CLV for all pending rows (before game-status gating) ──
    if HAS_ODDS_API:
        for idx, row in df.iterrows():
            if str(row['Result']).strip().upper() != 'PENDING':
                continue
            # Skip if CLV already populated
            if str(df.at[idx, 'ClosingLine']).strip():
                continue
            away_nick = row['Away'].strip()
            home_nick = row['Home'].strip()
            closing = get_closing_line(away_nick, home_nick)
            if closing is not None:
                df.at[idx, 'ClosingLine'] = str(closing)
                try:
                    market = float(row['Market'])
                    # CLV from bettor perspective: positive = you beat the close
                    # AWAY pick: CLV = closing - market (more negative close = got better points)
                    # HOME pick: CLV = market - closing (more negative close = gave fewer points)
                    raw_clv = round(closing - market, 2)
                    pick = str(row.get('Pick', '')).strip()
                    home = str(row.get('Home', '')).strip()
                    clv = -raw_clv if pick == home else raw_clv
                    df.at[idx, 'CLV'] = str(clv)
                except (ValueError, TypeError):
                    pass

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

        # Calculate Payout if Bet and Odds are present
        if 'Payout' in df.columns and 'Bet' in df.columns and 'Odds' in df.columns:
            payout = calc_payout(result, row.get('Bet', ''), row.get('Odds', ''))
            if payout is not None:
                df.at[idx, 'Payout'] = f"{payout:.2f}"

        # ── CLV: Closing Line Value (fill if not already populated above) ──
        if HAS_ODDS_API and not str(df.at[idx, 'ClosingLine']).strip():
            away_nick = row['Away'].strip()
            home_nick = row['Home'].strip()
            closing = get_closing_line(away_nick, home_nick)
            if closing is not None:
                df.at[idx, 'ClosingLine'] = str(closing)
                try:
                    market = float(row['Market'])
                    # CLV from bettor perspective (positive = beat the close)
                    raw_clv = round(closing - market, 2)
                    pick = str(row.get('Pick', '')).strip()
                    home = str(row.get('Home', '')).strip()
                    clv = -raw_clv if pick == home else raw_clv
                    df.at[idx, 'CLV'] = str(clv)
                except (ValueError, TypeError):
                    pass

        icon = '✅' if result == 'WIN' else ('🟰' if result == 'PUSH' else '❌')
        clv_str = ''
        if str(df.at[idx, 'CLV']).strip():
            try:
                clv_val = float(df.at[idx, 'CLV'])
                clv_str = f"  CLV: {clv_val:+.1f}"
            except (ValueError, TypeError):
                pass
        print(f"  {icon} {row['ID']}: {row['Away']} @ {row['Home']} → {result}  ({final_score}){clv_str}")
        updated += 1

    # Save updated CSV
    df.to_csv(filepath, index=False)

    print(f"\n  Summary: {updated} updated, {still_pending} still pending")
    print(f"  💾 Saved to {os.path.basename(filepath)}")


def main():
    print("\n" + "=" * 60)
    print("  📊 NBA Bet Tracker — Result Updater")
    print("=" * 60)

    # ── CLV status alert ──
    if not HAS_ODDS_API:
        print("\n  ⚠️  CLV tracking unavailable — odds_api module not found.")
        print("     Install python-dotenv and ensure odds_api.py is present.")
    elif not API_KEY:
        print("\n  ⚠️  CLV tracking unavailable — no ODDS_API_KEY in .env file.")
        print("     Run: cp .env.example .env  and add your key from the-odds-api.com")
    else:
        from odds_api import load_cache
        cache = load_cache()
        cached_count = len(cache.get('games', {}))
        if cached_count == 0:
            print("\n  ⚠️  No cached odds found — CLV columns will be blank.")
            print("     Run: bash fetch_all_nba_data.sh (before tip-off) to cache odds.")
        else:
            print(f"\n  ✅ CLV tracking active — {cached_count} game(s) in odds cache.")

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
