import os
import csv
import glob
import json
import subprocess
import time
from datetime import datetime, timedelta, date
from nba_analytics import predict_nba_spread, log_bet, get_cache_times, calculate_pace_and_ratings

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

# ── Schedule Cache (fully offline) ───────────────────────────────────────
SCHEDULE_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'nba_schedule_cache.json')
_schedule_cache = None  # in-memory singleton


def _load_schedule_cache():
    """Load schedule cache from disk once, then reuse in memory."""
    global _schedule_cache
    if _schedule_cache is not None:
        return _schedule_cache
    if os.path.exists(SCHEDULE_CACHE_FILE):
        try:
            with open(SCHEDULE_CACHE_FILE, 'r') as f:
                _schedule_cache = json.load(f)
            return _schedule_cache
        except (json.JSONDecodeError, IOError) as e:
            print(f"[!] Schedule cache unreadable: {e}")
    _schedule_cache = {}  # empty sentinel so we don't retry disk
    return _schedule_cache


def invalidate_schedule_cache():
    """Force reload from disk (called after a data refresh)."""
    global _schedule_cache
    _schedule_cache = None


def load_schedule_for_date(target_date):
    """Load games for a date from the prefetched schedule cache.
    Returns (games_list, source_label).  Zero network calls."""
    cache = _load_schedule_cache()
    date_key = target_date.isoformat()  # e.g. "2026-02-19"
    entry = cache.get('dates', {}).get(date_key)
    if entry and entry.get('games'):
        games = [(g['away'], g['home'], g.get('time', '')) for g in entry['games']]
        source = entry.get('source', 'Cache')
        return games, source
    return [], None


def display_bet_tracker():
    """List available bet tracker CSVs, let user pick one, and display a formatted summary."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    files = sorted(glob.glob(os.path.join(base_dir, 'bet_tracker_*.csv')))

    if not files:
        print("\n  📭 No bet tracker files found.")
        return

    print("\n📒 AVAILABLE BET TRACKERS")
    print("=" * 55)
    for i, f in enumerate(files, 1):
        fname = os.path.basename(f)
        # Count rows (excluding header)
        with open(f, 'r') as fh:
            row_count = max(0, sum(1 for _ in fh) - 1)
        print(f"  {i}. {fname}  ({row_count} bet{'s' if row_count != 1 else ''})")
    print(f"  A. All trackers combined")
    print("=" * 55)

    pick = input("Select tracker # (or A for all, Enter to cancel): ").strip().upper()
    if not pick:
        return

    if pick == 'A':
        selected_files = files
        label = "ALL TRACKERS COMBINED"
    else:
        try:
            idx = int(pick) - 1
            if idx < 0 or idx >= len(files):
                print("❌ Invalid selection.")
                return
            selected_files = [files[idx]]
            label = os.path.basename(files[idx])
        except ValueError:
            print("❌ Invalid selection.")
            return

    # Read and normalize all rows from selected files
    all_rows = []
    for filepath in selected_files:
        with open(filepath, 'r', newline='') as f:
            reader = csv.reader(f)
            rows = list(reader)
        if not rows:
            continue
        header = rows[0]
        data = rows[1:]
        # Detect format by header length and map to unified dict
        for row in data:
            if len(header) >= 20 and len(row) >= 20:
                # Current 20-col format
                all_rows.append({
                    'id': row[0], 'time': row[1], 'away': row[2], 'home': row[3],
                    'fair': row[4], 'market': row[5], 'edge': row[6],
                    'kelly': row[9], 'conf': row[10], 'pick': row[11],
                    'type': row[12], 'book': row[13], 'odds': row[14],
                    'bet': row[15], 'to_win': row[16], 'result': row[17],
                    'payout': row[18], 'notes': row[19] if len(row) > 19 else '',
                    'file': os.path.basename(filepath)
                })
            elif len(header) >= 18 and len(row) >= 18:
                # 18-col format
                all_rows.append({
                    'id': row[0], 'time': row[1], 'away': row[2], 'home': row[3],
                    'fair': row[4], 'market': row[5], 'edge': row[6],
                    'kelly': row[7], 'conf': row[8], 'pick': row[9],
                    'type': row[10], 'book': row[11], 'odds': row[12],
                    'bet': row[13], 'to_win': row[14], 'result': row[15],
                    'payout': row[16], 'notes': row[17] if len(row) > 17 else '',
                    'file': os.path.basename(filepath)
                })
            elif len(header) >= 14 and len(row) >= 14:
                # Old 14-col format
                all_rows.append({
                    'id': row[0], 'time': '', 'away': row[1], 'home': row[2],
                    'fair': row[3], 'market': row[4], 'edge': row[5],
                    'kelly': row[6], 'conf': '', 'pick': row[7],
                    'type': 'Spread', 'book': row[8], 'odds': row[9],
                    'bet': row[10], 'to_win': '', 'result': row[11],
                    'payout': row[12], 'notes': row[13] if len(row) > 13 else '',
                    'file': os.path.basename(filepath)
                })

    if not all_rows:
        print("\n  📭 No bets found in the selected tracker(s).")
        return

    # ── Display formatted table ──
    print(f"\n📊 BET TRACKER: {label}")
    print("=" * 110)
    id_w = 16 if len(selected_files) > 1 else 5
    print(f"  {'ID':<{id_w}} {'Matchup':<30} {'Pick':<14} {'Edge':<7} {'Odds':<7} {'Bet':>7} {'Result':<8} {'Payout':>8}")
    print(f"  {'-'*id_w} {'-'*30} {'-'*14} {'-'*7} {'-'*7} {'-'*7:>7} {'-'*8} {'-'*8:>8}")

    total_wagered = 0.0
    total_payout = 0.0
    wins, losses, pending = 0, 0, 0

    for r in all_rows:
        matchup = f"{r['away']} @ {r['home']}"
        if len(matchup) > 28:
            matchup = matchup[:27] + '…'

        result_str = r['result']
        if result_str == 'WIN':
            result_display = '✅ WIN'
            wins += 1
        elif result_str == 'LOSS':
            result_display = '❌ LOSS'
            losses += 1
        elif result_str == 'PUSH':
            result_display = '➡️  PUSH'
            wins += 0  # neutral
        else:
            result_display = '⏳ PEND'
            pending += 1

        # Parse numeric values
        try:
            bet_val = float(r['bet']) if r['bet'] else 0.0
        except ValueError:
            bet_val = 0.0
        try:
            payout_val = float(r['payout']) if r['payout'] else 0.0
        except ValueError:
            payout_val = 0.0

        total_wagered += bet_val
        total_payout += payout_val

        bet_str = f"${bet_val:.0f}" if bet_val else '-'
        payout_str = f"${payout_val:+.2f}" if r['payout'] else '-'
        odds_str = r['odds'] if r['odds'] else '-'
        edge_str = r['edge'] if r['edge'] else '-'

        # File tag when showing combined
        file_id = r['id']
        if len(selected_files) > 1:
            # Extract date from filename for compact tag
            date_part = r['file'].replace('bet_tracker_', '').replace('.csv', '')
            file_id = f"{date_part}/{r['id']}"

        print(f"  {file_id:<{id_w}} {matchup:<30} {r['pick']:<14} {edge_str:<7} {odds_str:<7} {bet_str:>7} {result_display:<8} {payout_str:>8}")

        # Show notes if present
        if r['notes']:
            print(f"  {' ' * id_w} 📝 {r['notes']}")

    # ── Summary ──
    print("=" * 110)
    total_bets = wins + losses + pending
    net = total_payout
    win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0.0
    roi = (net / total_wagered * 100) if total_wagered > 0 else 0.0

    net_color = '🟢' if net >= 0 else '🔴'
    print(f"  📈 SUMMARY: {total_bets} bet{'s' if total_bets != 1 else ''} | "
          f"{wins}W - {losses}L{f' - {pending}P' if pending else ''} | "
          f"Win Rate: {win_rate:.1f}%")
    print(f"  💰 Wagered: ${total_wagered:.0f} | "
          f"Net P&L: {net_color} ${net:+.2f} | "
          f"ROI: {roi:+.1f}%")
    print("=" * 110)


STALE_THRESHOLD_HOURS = int(os.environ.get('STALE_HOURS', 12))


def _check_cache_staleness(cache_times):
    """Return list of cache names that are stale, missing, or unknown."""
    stale, missing = [], []
    now = datetime.now()
    for key, label in [('stats', 'Team Stats'), ('injuries', 'Injuries'),
                       ('news', 'News'), ('rest', 'Rest Penalty'),
                       ('schedule', 'Schedule'), ('star_tax', 'Star Tax')]:
        val, _src = cache_times.get(key, ('Missing', ''))
        if val in ('Missing',):
            missing.append(label)
            continue
        if val in ('Unknown',):
            stale.append(label)
            continue
        # Try to parse the timestamp
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%dT%H:%M:%S'):
            try:
                ts = datetime.strptime(val.strip(), fmt)
                age_hours = (now - ts).total_seconds() / 3600
                if age_hours > STALE_THRESHOLD_HOURS:
                    stale.append(f"{label} ({int(age_hours)}h old)")
                break
            except ValueError:
                continue
    return stale, missing


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
            for label, key in [('Team Stats', 'stats'), ('Injuries', 'injuries'),
                                ('News', 'news'), ('Rest Penalty', 'rest'),
                                ('Schedule', 'schedule'), ('Star Tax', 'star_tax')]:
                ts, src = cache_times.get(key, ('Unknown', ''))
                src_tag = f"  ({src})" if src else ""
                print(f"  {label + ':':<14} {ts}{src_tag}")
            print("="*75)

            # Warn if any cache data is stale or missing
            stale, missing = _check_cache_staleness(cache_times)
            if missing:
                print(f"  🚨 MISSING CACHE: {', '.join(missing)}")
                print(f"     → Run [R] to refresh or: bash fetch_all_nba_data.sh")
            if stale:
                print(f"  ⚠️  STALE DATA (>{STALE_THRESHOLD_HOURS}h): {', '.join(stale)}")
                print(f"     → Run [R] to refresh or: bash fetch_all_nba_data.sh")

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
            print("COMMANDS: [G#] (Analyze) | [U] (Upcoming) | [B] (Bets) | [R] (Refresh) | [C] (Custom) | [Q] (Quit)")
            choice = input("Enter Command: ").upper()

            if choice == 'Q':
                print("Shutting down. Happy Betting!")
                break

            elif choice == 'B':
                display_bet_tracker()
                continue

            elif choice == 'R':
                print("\n🔄 Refreshing all NBA data (stats, injuries, news, rest, schedule)...")
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
                    invalidate_schedule_cache()
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
                print("COMMANDS: [G#/U#] (Analyze) | [B] (Bets) | [R] (Refresh) | [C] (Custom) | [Q] (Quit)")
                choice = input("Enter Command: ").upper()

                if choice == 'Q':
                    print("Shutting down. Happy Betting!")
                    break
                elif choice == 'B':
                    display_bet_tracker()
                    continue
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
        print("\n[EXIT] Keyboard interrupt received. Shutting down gracefully. Happy Betting!")

if __name__ == "__main__":
    run_ui()
