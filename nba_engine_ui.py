import os
import json
import subprocess
import time
from datetime import datetime, timedelta, date
from nba_api.stats.endpoints import scoreboardv2
from nba_api.stats.static import teams
from nba_analytics import predict_nba_spread, log_bet, get_cache_times, calculate_pace_and_ratings
from schedule_scraper import scrape_espn, normalize_team

DEFAULT_EDGE_CAP = 10

def load_edge_cap():
    """Load edge cap from bankroll.json, falling back to default."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bankroll.json')
    try:
        with open(path) as f:
            return json.load(f).get('edge_cap', DEFAULT_EDGE_CAP)
    except (FileNotFoundError, json.JSONDecodeError):
        return DEFAULT_EDGE_CAP

def calculate_kelly(market, fair_line):
    """Conservative Quarter-Kelly Criterion bankroll management."""
    b, edge = 0.91, abs(fair_line - market)
    prob = min(0.70, max(0.48, 0.524 + (edge * 0.015)))
    kelly_f = ((b * prob) - (1 - prob)) / b
    return round(max(0, kelly_f * 0.25) * 100, 2)

# ── Team ID lookup for ScoreboardV2 ──────────────────────────────────────
_ALL_TEAMS = teams.get_teams()
_TEAM_ID_TO_NAME = {t['id']: t['full_name'] for t in _ALL_TEAMS}


def fetch_games_scoreboardv2(target_date):
    """Fetch games from nba_api ScoreboardV2 for a given date.
    Returns list of (away_name, home_name, status_text) tuples."""
    try:
        sb = scoreboardv2.ScoreboardV2(
            game_date=target_date.strftime('%Y-%m-%d'),
            league_id='00',
            day_offset=0
        )
        header = sb.game_header.get_dict()
        headers_list = header['headers']
        rows = header['data']

        home_idx = headers_list.index('HOME_TEAM_ID')
        away_idx = headers_list.index('VISITOR_TEAM_ID')
        status_idx = headers_list.index('GAME_STATUS_TEXT')

        games = []
        seen = set()
        for row in rows:
            away = _TEAM_ID_TO_NAME.get(row[away_idx], str(row[away_idx]))
            home = _TEAM_ID_TO_NAME.get(row[home_idx], str(row[home_idx]))
            status = row[status_idx]
            key = (away, home)
            if key not in seen:
                seen.add(key)
                games.append((away, home, status))
        return games
    except Exception as e:
        return None  # Signal caller to try fallback


def fetch_games_espn(target_date):
    """Fallback: scrape ESPN schedule for a given date.
    Returns list of (away_name, home_name, status_text) tuples."""
    try:
        espn_games = scrape_espn(target_date)
        return [(g['away'], g['home'], g.get('time', '')) for g in espn_games]
    except Exception:
        return []


def load_schedule_for_date(target_date):
    """Load games for a date: ScoreboardV2 primary, ESPN fallback.
    Returns (games_list, source_label)."""
    games = fetch_games_scoreboardv2(target_date)
    if games is not None and len(games) > 0:
        return games, 'NBA API'

    # Fallback to ESPN
    games = fetch_games_espn(target_date)
    if games:
        return games, 'ESPN'

    return [], None


def run_ui():
    today_display = datetime.now().strftime("%B %d, %Y")
    custom_counter = 0  # Unique counter for custom matchup GIDs

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
            today = date.today()
            games, source = load_schedule_for_date(today)

            if games:
                if source:
                    print(f"📡 Source: {source}")
                for i, (away, home, status) in enumerate(games):
                    gid = f"G{i+1}"
                    schedule[gid] = (away, home)
                    print(f"{gid:<4} {away:<24} @ {home:<24} {status}")
            else:
                print("📅 No games scheduled today (All-Star break or off day).")
                print("💡 TIP: Type 'U' to view upcoming games, or 'C' for a custom matchup.")

            print("-" * 75)
            print("COMMANDS: [G#] (Analyze) | [U] (Upcoming) | [R] (Refresh) | [C] (Custom) | [Q] (Quit)")
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

            elif choice == 'U':
                # ── Upcoming Games (next 7 days) ──
                print("\n📆 UPCOMING NBA SCHEDULE")
                print("=" * 75)
                upcoming_schedule = {}
                game_counter = 0

                for day_offset in range(1, 8):
                    future_date = today + timedelta(days=day_offset)
                    day_games, src = load_schedule_for_date(future_date)
                    if not day_games:
                        continue

                    day_label = future_date.strftime('%A, %B %-d')
                    src_tag = f" ({src})" if src else ""
                    print(f"\n  {day_label}{src_tag}")
                    print(f"  {'-' * 65}")

                    for away, home, status in day_games:
                        game_counter += 1
                        gid = f"U{game_counter}"
                        upcoming_schedule[gid] = (away, home)
                        print(f"  {gid:<5} {away:<24} @ {home:<24} {status}")

                if not upcoming_schedule:
                    print("  No upcoming games found for the next 7 days.")
                else:
                    # Merge upcoming into schedule so user can analyze them
                    schedule.update(upcoming_schedule)
                    print(f"\n  💡 Total: {game_counter} games over the next 7 days")
                    print(f"  💡 Type a game ID (e.g., U1) to analyze any upcoming matchup.")

                print("=" * 75)
                # Don't loop back to redraw — let user pick from combined schedule
                print("-" * 75)
                print("COMMANDS: [G#/U#] (Analyze) | [R] (Refresh) | [C] (Custom) | [Q] (Quit)")
                choice = input("Enter Command: ").upper()

                if choice == 'Q':
                    print("Shutting down. Good luck tonight, Johnny!")
                    break
                elif choice in schedule or choice == 'C':
                    # Fall through to the analysis handler below
                    pass
                else:
                    print("❌ Command not recognized.")
                    continue

            if choice in schedule or choice == 'C':
                is_upcoming = choice.startswith('U')

                if choice == 'C':
                    custom_counter += 1
                    gid = f"C{custom_counter}"
                    away = input("Enter Away Team Name: ")
                    home = input("Enter Home Team Name: ")
                else:
                    gid = choice
                    away, home = schedule[choice]

                if is_upcoming:
                    print(f"\n[PREVIEW] {away} vs {home} (upcoming game — research mode)")
                else:
                    print(f"\n[ANALYZING] {away} vs {home}...")

                try:
                    line_in = input(f"Market Line for {home} (e.g., -5.5): ").strip()
                    if not line_in:
                        print("❌ No market line entered. Returning to scoreboard.")
                        continue
                    try:
                        market = float(line_in)
                    except ValueError:
                        print(f"❌ Invalid market line '{line_in}'. Must be a number (e.g., -5.5).")
                        continue


                    # Pro Logic: Injury Star Tax + Fatigue + HCA + late-breaking flag
                    fair_line, q_players, news, flag, star_tax_failed = predict_nba_spread(away, home)
                    raw_edge = round(abs(fair_line - market), 2)
                    EDGE_CAP = load_edge_cap()
                    edge = min(raw_edge, EDGE_CAP)
                    edge_capped = raw_edge > EDGE_CAP
                    kelly = calculate_kelly(market, fair_line)

                    # Confidence Grade Logic
                    conf = "HIGH"
                    if star_tax_failed: conf = "MEDIUM (Star Tax API failed — injury impact unknown)"
                    elif len(q_players) >= 2: conf = "LOW (High Injury Volatility)"
                    elif len(q_players) == 1: conf = "MEDIUM"

                    print("\n" + "•"*45)
                    print(f"PRO ENGINE LINE: {fair_line}")
                    print(f"MARKET SPREAD:   {market}")
                    if edge_capped:
                        print(f"CALCULATED EDGE: {edge} pts (capped from {raw_edge})")
                    else:
                        print(f"CALCULATED EDGE: {edge} pts")
                    print(f"KELLY SUGGESTION: Risk {kelly}% of Bankroll")
                    print(f"MODEL CONFIDENCE: {conf}")
                    print("•"*45)

                    if edge_capped:
                        print(f"⚠️  EDGE CAP HIT: Raw edge was {raw_edge} pts — model may be missing key info.")
                        print(f"   → Large edges often mean the market knows something the model doesn't.")
                        print(f"   → Investigate injuries, motivation, or lineup news before betting.")

                    if q_players:
                        print(f"⚠️  GTD/QUESTIONABLE: {', '.join(q_players)}")
                    if flag:
                        print(f"🚨 ALERT: Late-breaking lineup/injury news detected! Double-check before betting.")
                    if star_tax_failed:
                        print(f"⚠️  STAR TAX WARNING: Could not fetch player On/Off data. Injury impact NOT reflected in line.")
                        print(f"   → Manually verify key player statuses before placing this bet.")

                    recommendation = home if fair_line < market else away
                    if edge_capped:
                        print(f"🚨 REVIEW REQUIRED: {recommendation} (edge capped at {EDGE_CAP} — verify before betting)")
                    elif edge >= 5 and "HIGH" in conf:
                        print(f"🔥 STRONG SIGNAL: Bet {recommendation}")
                    elif edge >= 3:
                        print(f"📊 LEAN: {recommendation} (moderate edge)")
                    else:
                        print(f"📉 LOW EDGE: {recommendation} (thin margin — proceed with caution)")

                    if is_upcoming:
                        # Preview mode — don't log to bet tracker
                        print("\n  📋 PREVIEW ONLY — This is an upcoming game.")
                        print("     Data may change by game day (injuries, lines, rest).")
                        print("     Re-analyze on game day to log a bet.")
                        print(f"\n[PREVIEW COMPLETE] Returning to Scoreboard...")
                    else:
                        # Live game — full logging flow
                        print("\n  📝 Log bet details (press Enter to skip any):")
                        pick_in = input(f"     Betting on [{recommendation}] or override (type team name): ").strip()
                        pick = pick_in if pick_in else recommendation
                        bet_type = input("     Bet type (S=Spread, M=Moneyline, O=Over/Under) [S]: ").strip().upper()
                        bet_type = {'S': 'Spread', 'M': 'Moneyline', 'O': 'Over/Under'}.get(bet_type, 'Spread')
                        book = input("     Sportsbook (e.g., DraftKings, FanDuel): ").strip()
                        odds_in = input("     Odds (e.g., -110): ").strip()
                        bet_in = input("     Bet amount in $ (e.g., 50): ").strip()

                        odds_val = odds_in if odds_in else ''
                        bet_val = bet_in if bet_in else ''

                        # Log to date-stamped CSV
                        log_bet(gid, away, home, fair_line, market, edge, pick, kelly, conf, bet_type, book, odds_val, bet_val, raw_edge=raw_edge, edge_capped=edge_capped)

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
