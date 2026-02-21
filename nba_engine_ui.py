import os
import csv
import glob
import json
import re
import subprocess
import time
from datetime import datetime, timedelta, date
from nba_analytics import predict_nba_spread, log_bet, get_cache_times, calculate_pace_and_ratings, get_injuries

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
    from schedule_scraper import normalize_team as _norm
    cache = _load_schedule_cache()
    date_key = target_date.isoformat()  # e.g. "2026-02-19"
    entry = cache.get('dates', {}).get(date_key)
    if entry and entry.get('games'):
        games = []
        for g in entry['games']:
            away = _norm(g['away'].strip()) if g.get('away') else g.get('away', '')
            home = _norm(g['home'].strip()) if g.get('home') else g.get('home', '')
            time_str = g.get('time', '').strip()
            games.append((away, home, time_str))
        source = entry.get('source', 'Cache')
        return games, source
    return [], None


def display_bet_tracker():
    """List available bet tracker CSVs, let user pick one, and display a formatted summary.
    Loops back to the tracker list after each display until user presses Enter or Q."""
    base_dir = os.path.dirname(os.path.abspath(__file__))

    while True:
        files = sorted(glob.glob(os.path.join(base_dir, 'bet_tracker_*.csv')))

        if not files:
            print("\n  📭 No bet tracker files found.")
            return

        print("\n📒 AVAILABLE BET TRACKERS")
        print("=" * 55)
        for i, f in enumerate(files, 1):
            fname = os.path.basename(f)
            with open(f, 'r') as fh:
                row_count = max(0, sum(1 for _ in fh) - 1)
            print(f"  {i}. {fname}  ({row_count} bet{'s' if row_count != 1 else ''})")
        print(f"  A. All trackers combined")
        print(f"  Q. Back to main menu")
        print("=" * 55)

        pick = input("Select tracker # (or A for all, Q to go back): ").strip().upper()
        if not pick or pick == 'Q':
            return

        if pick == 'A':
            selected_files = files
            label = "ALL TRACKERS COMBINED"
        else:
            try:
                idx = int(pick) - 1
                if idx < 0 or idx >= len(files):
                    print("❌ Invalid selection.")
                    continue
                selected_files = [files[idx]]
                label = os.path.basename(files[idx])
            except ValueError:
                print("❌ Invalid selection.")
                continue

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
            # Build a header-index map for flexible CLV/ClosingLine column lookup
            hmap = {h.strip(): i for i, h in enumerate(header)}
            for row in data:
                base = None
                if len(header) >= 20 and len(row) >= 20:
                    # Current 20-col format
                    base = {
                        'id': row[0], 'time': row[1], 'away': row[2], 'home': row[3],
                        'fair': row[4], 'market': row[5], 'edge': row[6],
                        'kelly': row[9], 'conf': row[10], 'pick': row[11],
                        'type': row[12], 'book': row[13], 'odds': row[14],
                        'bet': row[15], 'to_win': row[16], 'result': row[17],
                        'payout': row[18], 'notes': row[19] if len(row) > 19 else '',
                        'file': os.path.basename(filepath)
                    }
                elif len(header) >= 18 and len(row) >= 18:
                    # 18-col format
                    base = {
                        'id': row[0], 'time': row[1], 'away': row[2], 'home': row[3],
                        'fair': row[4], 'market': row[5], 'edge': row[6],
                        'kelly': row[7], 'conf': row[8], 'pick': row[9],
                        'type': row[10], 'book': row[11], 'odds': row[12],
                        'bet': row[13], 'to_win': row[14], 'result': row[15],
                        'payout': row[16], 'notes': row[17] if len(row) > 17 else '',
                        'file': os.path.basename(filepath)
                    }
                elif len(header) >= 14 and len(row) >= 14:
                    # Old 14-col format
                    base = {
                        'id': row[0], 'time': '', 'away': row[1], 'home': row[2],
                        'fair': row[3], 'market': row[4], 'edge': row[5],
                        'kelly': row[6], 'conf': '', 'pick': row[7],
                        'type': 'Spread', 'book': row[8], 'odds': row[9],
                        'bet': row[10], 'to_win': '', 'result': row[11],
                        'payout': row[12], 'notes': row[13] if len(row) > 13 else '',
                        'file': os.path.basename(filepath)
                    }
                if base:
                    # Attach CLV columns if present (added by update_results.py)
                    cl_idx = hmap.get('ClosingLine')
                    clv_idx = hmap.get('CLV')
                    base['closing_line'] = row[cl_idx].strip() if cl_idx is not None and cl_idx < len(row) else ''
                    base['clv'] = row[clv_idx].strip() if clv_idx is not None and clv_idx < len(row) else ''
                    # Attach preflight status if present
                    pfc_idx = hmap.get('PreflightCheck')
                    pfn_idx = hmap.get('PreflightNote')
                    base['preflight'] = row[pfc_idx].strip() if pfc_idx is not None and pfc_idx < len(row) else ''
                    base['preflight_note'] = row[pfn_idx].strip() if pfn_idx is not None and pfn_idx < len(row) else ''
                    all_rows.append(base)

        if not all_rows:
            print("\n  📭 No bets found in the selected tracker(s).")
            continue

        # ── Display formatted table ──
        print(f"\n📊 BET TRACKER: {label}")
        print("=" * 120)
        id_w = 16 if len(selected_files) > 1 else 5
        print(f"  {'ID':<{id_w}} {'Matchup':<30} {'Pick':<14} {'Edge':<7} {'Odds':<7} {'Bet':>7} {'Result':<8} {'Payout':>8}  {'CLV':<10}")
        print(f"  {'-'*id_w} {'-'*30} {'-'*14} {'-'*7} {'-'*7} {'-'*7:>7} {'-'*8} {'-'*8:>8}  {'-'*10}")

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

            # CLV display: show value with indicator, or pending status
            clv_raw = r.get('clv', '')
            if clv_raw:
                try:
                    clv_val = float(clv_raw)
                    if clv_val > 0:
                        clv_display = f"✅ +{clv_val:.1f}"
                    elif clv_val < 0:
                        clv_display = f"❌ {clv_val:.1f}"
                    else:
                        clv_display = "➡️  0.0"
                except ValueError:
                    clv_display = clv_raw
            elif result_str == 'PENDING':
                clv_display = "⏳ Pending"
            else:
                clv_display = "—  N/A"

            # File tag when showing combined
            file_id = r['id']
            if len(selected_files) > 1:
                # Extract date from filename for compact tag
                date_part = r['file'].replace('bet_tracker_', '').replace('.csv', '')
                file_id = f"{date_part}/{r['id']}"

            print(f"  {file_id:<{id_w}} {matchup:<30} {r['pick']:<14} {edge_str:<7} {odds_str:<7} {bet_str:>7} {result_display:<8} {payout_str:>8}  {clv_display}")

            # Show notes if present
            if r['notes']:
                print(f"  {' ' * id_w} 📝 {r['notes']}")

        # ── Summary ──
        print("=" * 120)
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

        # CLV summary
        clv_values = []
        clv_missing = 0
        for r in all_rows:
            clv_raw = r.get('clv', '')
            if clv_raw:
                try:
                    clv_values.append(float(clv_raw))
                except ValueError:
                    pass
            elif r.get('result', '') != 'PENDING':
                clv_missing += 1
        if clv_values:
            avg_clv = sum(clv_values) / len(clv_values)
            pos_clv = sum(1 for v in clv_values if v > 0)
            clv_color = '🟢' if avg_clv >= 0 else '🔴'
            print(f"  📈 CLV: {clv_color} Avg {avg_clv:+.1f} | "
                  f"Positive: {pos_clv}/{len(clv_values)} ({pos_clv/len(clv_values)*100:.0f}%)"
                  f"{f' | {clv_missing} bets missing CLV' if clv_missing else ''}")
        elif pending == total_bets:
            print(f"  📈 CLV: ⏳ All bets pending — run ./fetch_all_nba_data.sh odds before tip-off, then update_results.py after")
        elif clv_missing:
            print(f"  📈 CLV: ⚠️  {clv_missing} decided bet{'s' if clv_missing != 1 else ''} missing CLV — were odds fetched before tip-off?")

        # Preflight status summary
        pf_stamped = sum(1 for r in all_rows if r.get('preflight'))
        pf_total = len(all_rows)
        if pf_stamped == pf_total and pf_total > 0:
            print(f"  🛡️  Preflight: ✅ All {pf_total} bet(s) verified")
        elif pf_stamped > 0:
            print(f"  🛡️  Preflight: ⚠️  {pf_stamped}/{pf_total} verified — {pf_total - pf_stamped} unstamped")
        else:
            # Check if any row has a preflight_note (backfilled historical)
            has_notes = any(r.get('preflight_note') for r in all_rows)
            if has_notes:
                print(f"  🛡️  Preflight: ℹ️  Historical tracker — retroactive validation not available")
            # else: columns might not exist yet, skip silently

        print("=" * 120)


# ── Bet Validation Audit ─────────────────────────────────────────────────
def validate_historical_bets():
    """Audit all bet trackers for internal consistency — verifies that the
    recorded model outputs (Fair, Market, Edge, Kelly, Pick) are mathematically
    self-consistent.  Flags bets that may have been placed on bad data.

    NOTE: We cannot re-run the prediction model for historical bets because
    all input data (stats, injuries, rest, star tax, odds) is ephemeral and
    overwritten daily.  Instead, we validate the RECORDED values against the
    known formulas that produced them."""

    base_dir = os.path.dirname(os.path.abspath(__file__))
    files = sorted(glob.glob(os.path.join(base_dir, 'bet_tracker_*.csv')))

    if not files:
        print("\n  📭 No bet tracker files found.")
        return

    EDGE_CAP = load_edge_cap()

    print("\n" + "=" * 100)
    print("  🔍 BET VALIDATION AUDIT — Internal Consistency Check")
    print("=" * 100)
    print("  Validates recorded model outputs against known formulas.")
    print("  ⚠️  Cannot re-run predictions — historical cache data is overwritten daily.")
    print("  Instead checks: Edge math, Kelly math, pick direction, preflight status,")
    print("  and cross-references results to identify data-quality patterns.")
    print("=" * 100)

    all_issues = []          # (file, gid, severity, message)
    file_summaries = []      # per-file summary tuples
    # Aggregate stats for preflight-vs-no-preflight comparison
    pf_results = {'verified': {'W': 0, 'L': 0, 'P': 0}, 'unverified': {'W': 0, 'L': 0, 'P': 0}}

    for filepath in files:
        fname = os.path.basename(filepath)
        with open(filepath, 'r', newline='') as f:
            reader = csv.reader(f)
            rows_raw = list(reader)
        if len(rows_raw) < 2:
            file_summaries.append((fname, 0, 0, 0, 0))
            continue

        header = rows_raw[0]
        data = rows_raw[1:]
        hmap = {h.strip(): i for i, h in enumerate(header)}

        def _get(row, col, default=''):
            idx = hmap.get(col)
            if idx is not None and idx < len(row):
                return row[idx].strip()
            return default

        n_bets = len(data)
        n_errors = 0       # hard math failures
        n_warnings = 0     # soft concerns
        n_clean = 0

        for row in data:
            gid = _get(row, 'ID', '?')
            tag = f"{fname}/{gid}"

            fair_s = _get(row, 'Fair')
            market_s = _get(row, 'Market')
            edge_s = _get(row, 'Edge')
            raw_edge_s = _get(row, 'Raw_Edge')
            edge_capped_s = _get(row, 'Edge_Capped')
            kelly_s = _get(row, 'Kelly')
            pick = _get(row, 'Pick')
            away = _get(row, 'Away')
            home = _get(row, 'Home')
            result = _get(row, 'Result')
            preflight = _get(row, 'PreflightCheck')
            preflight_note = _get(row, 'PreflightNote')
            conf = _get(row, 'Confidence')

            row_issues = []

            # ── 1. Parse core numerics ──────────────────────────────────
            try:
                fair = float(fair_s)
            except (ValueError, TypeError):
                if fair_s:
                    row_issues.append(('ERROR', f'Fair={fair_s!r} non-numeric'))
                fair = None
            try:
                market = float(market_s)
            except (ValueError, TypeError):
                if market_s:
                    row_issues.append(('ERROR', f'Market={market_s!r} non-numeric'))
                market = None
            try:
                edge_recorded = float(edge_s)
            except (ValueError, TypeError):
                edge_recorded = None

            # ── 2. Edge math: Edge ≈ |Fair - Market| (or capped) ───────
            if fair is not None and market is not None:
                expected_raw_edge = round(abs(fair - market), 2)

                # Check raw edge if available
                if raw_edge_s:
                    try:
                        raw_edge_val = float(raw_edge_s)
                        if abs(raw_edge_val - expected_raw_edge) > 0.05:
                            row_issues.append(('ERROR', f'Raw_Edge={raw_edge_val} ≠ |Fair−Market|={expected_raw_edge}'))
                    except ValueError:
                        pass

                expected_edge = min(expected_raw_edge, EDGE_CAP)
                if edge_recorded is not None:
                    if abs(edge_recorded - expected_edge) > 0.05:
                        # Allow for different edge cap at the time
                        if abs(edge_recorded - expected_raw_edge) > 0.05:
                            row_issues.append(('ERROR', f'Edge={edge_recorded} ≠ expected {expected_edge} (|Fair−Market|={expected_raw_edge})'))

                # ── 3. Kelly math ───────────────────────────────────────
                if kelly_s:
                    try:
                        kelly_recorded = float(kelly_s.rstrip('%'))
                        # For edge-capped bets, use the capped edge for Kelly comparison
                        # calculate_kelly uses abs(fair-market) internally, so synthesize
                        # a "capped fair" that produces the right capped edge
                        effective_edge = expected_edge if edge_recorded is None else edge_recorded
                        if effective_edge < expected_raw_edge:
                            # Capped — build a synthetic fair for Kelly calc
                            capped_fair = market + effective_edge if fair > market else market - effective_edge
                        else:
                            capped_fair = fair
                        expected_kelly = calculate_kelly(market, capped_fair)
                        if abs(kelly_recorded - expected_kelly) > 0.1:
                            row_issues.append(('WARN', f'Kelly={kelly_recorded}% ≠ expected {expected_kelly}% (drift={kelly_recorded - expected_kelly:+.2f})'))
                    except ValueError:
                        row_issues.append(('WARN', f'Kelly={kelly_s!r} unparseable'))

                # ── 4. Pick direction ───────────────────────────────────
                if pick and pick not in (away, home):
                    row_issues.append(('ERROR', f'Pick={pick!r} not in {{Away={away!r}, Home={home!r}}}'))
                elif pick and away and home:
                    # Model recommends home if fair < market, away if fair >= market
                    expected_rec = home if fair < market else away
                    if pick != expected_rec:
                        # Not an error — user can override, but worth noting
                        row_issues.append(('INFO', f'Pick={pick} differs from model rec={expected_rec} (user override)'))

                # ── 5. Edge cap consistency ─────────────────────────────
                if edge_capped_s:
                    if edge_capped_s.upper() == 'YES' and expected_raw_edge <= EDGE_CAP:
                        row_issues.append(('WARN', f'Edge_Capped=YES but raw edge {expected_raw_edge} ≤ cap {EDGE_CAP}'))
                    elif edge_capped_s.upper() == 'NO' and expected_raw_edge > EDGE_CAP:
                        row_issues.append(('WARN', f'Edge_Capped=NO but raw edge {expected_raw_edge} > cap {EDGE_CAP}'))

            # ── 6. Preflight status ─────────────────────────────────────
            if not preflight and not preflight_note:
                row_issues.append(('WARN', 'No preflight stamp or note'))
            elif preflight_note and 'Historical' in preflight_note:
                row_issues.append(('INFO', 'Historical — cannot retroactively validate'))

            # ── 7. Result tracking for preflight comparison ─────────────
            if result in ('WIN', 'LOSS', 'PUSH'):
                bucket = 'verified' if preflight else 'unverified'
                key = result[0]  # W, L, P
                pf_results[bucket][key] += 1

            # Tally
            has_error = any(sev == 'ERROR' for sev, _ in row_issues)
            has_warn = any(sev == 'WARN' for sev, _ in row_issues)
            if has_error:
                n_errors += 1
            elif has_warn:
                n_warnings += 1
            else:
                n_clean += 1

            for sev, msg in row_issues:
                all_issues.append((fname, gid, sev, msg))

        file_summaries.append((fname, n_bets, n_clean, n_warnings, n_errors))

    # ══════════════════════════════════════════════════════════════════════
    #  Display results
    # ══════════════════════════════════════════════════════════════════════
    today_str = datetime.now().strftime('%Y-%m-%d')
    total_bets = sum(s[1] for s in file_summaries)

    print(f"\n  📋 TRACKER SUMMARY ({len(files)} file(s), {total_bets} total bets)")
    print(f"  {'Tracker':<35} {'Bets':>5}  {'Clean':>6}  {'Warn':>5}  {'Error':>6}")
    print(f"  {'-'*35} {'-'*5}  {'-'*6}  {'-'*5}  {'-'*6}")
    for fname, n_bets, n_clean, n_warn, n_err in file_summaries:
        is_today = today_str in fname
        marker = '📌' if is_today else '  '
        err_icon = '❌' if n_err else ('⚠️ ' if n_warn else '✅')
        print(f"  {marker}{err_icon} {fname:<31} {n_bets:>5}  {n_clean:>6}  {n_warn:>5}  {n_err:>6}")

    # ── Issues detail ────────────────────────────────────────────────────
    errors = [(f, g, s, m) for f, g, s, m in all_issues if s == 'ERROR']
    warnings = [(f, g, s, m) for f, g, s, m in all_issues if s == 'WARN']
    infos = [(f, g, s, m) for f, g, s, m in all_issues if s == 'INFO']

    if errors:
        print(f"\n  ❌ ERRORS ({len(errors)}) — Math inconsistencies in recorded data:")
        for f, g, sev, msg in errors[:15]:
            print(f"     {f}/{g}: {msg}")
        if len(errors) > 15:
            print(f"     ... and {len(errors) - 15} more")

    if warnings:
        print(f"\n  ⚠️  WARNINGS ({len(warnings)}) — Data-quality concerns:")
        for f, g, sev, msg in warnings[:15]:
            print(f"     {f}/{g}: {msg}")
        if len(warnings) > 15:
            print(f"     ... and {len(warnings) - 15} more")

    if infos:
        print(f"\n  ℹ️  INFO ({len(infos)}):")
        for f, g, sev, msg in infos[:10]:
            print(f"     {f}/{g}: {msg}")
        if len(infos) > 10:
            print(f"     ... and {len(infos) - 10} more")

    # ── Preflight vs non-preflight performance comparison ────────────────
    v_w = pf_results['verified']['W']
    v_l = pf_results['verified']['L']
    u_w = pf_results['unverified']['W']
    u_l = pf_results['unverified']['L']
    v_total = v_w + v_l
    u_total = u_w + u_l

    if v_total > 0 or u_total > 0:
        print(f"\n  📊 PREFLIGHT vs NON-PREFLIGHT PERFORMANCE:")
        if v_total > 0:
            v_rate = v_w / v_total * 100
            print(f"     ✅ Verified bets:   {v_w}W-{v_l}L ({v_rate:.1f}% win rate)")
        else:
            print(f"     ✅ Verified bets:   No decided bets yet")
        if u_total > 0:
            u_rate = u_w / u_total * 100
            print(f"     ⚠️  Unverified bets: {u_w}W-{u_l}L ({u_rate:.1f}% win rate)")
        else:
            print(f"     ⚠️  Unverified bets: No decided bets yet")
        if v_total > 0 and u_total > 0:
            diff = (v_w / v_total * 100) - (u_w / u_total * 100)
            if diff > 0:
                print(f"     → Verified bets outperform by {diff:+.1f}pp")
            elif diff < 0:
                print(f"     → Unverified bets outperform by {abs(diff):.1f}pp (small sample?)")
            else:
                print(f"     → Identical win rates")

    # ── Verdict ──────────────────────────────────────────────────────────
    print("\n" + "=" * 100)
    if errors:
        print(f"  🔴 AUDIT RESULT: {len(errors)} bet(s) have math inconsistencies in recorded data.")
        print(f"     These bets may have been placed with stale or corrupted inputs.")
        print(f"     Review the errors above — the recorded Fair/Market/Edge values don't add up.")
    elif warnings:
        print(f"  🟡 AUDIT RESULT: All math checks pass. {len(warnings)} warning(s) to review.")
        if any('No preflight' in m for _, _, _, m in warnings):
            print(f"     Some bets lack preflight verification — run: python preflight_check.py --backfill")
    else:
        print(f"  🟢 AUDIT RESULT: All {total_bets} bet(s) internally consistent. No anomalies detected.")
    print("=" * 100)

    input("\n  Press Enter to return to the main menu...")


# ── Pre-Tipoff Review ────────────────────────────────────────────────────
def display_pretipoff_review():
    """Compare fresh post-fetch data against placed bets.
    Shows injury changes, line movement, updated edge, and action suggestions."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    today = date.today()
    tracker_path = os.path.join(base_dir, f"bet_tracker_{today.isoformat()}.csv")

    if not os.path.exists(tracker_path):
        print("\n  📭 No bets placed today — nothing to review.")
        print("     Analyze a game first with [G#] then come back here.")
        return

    # ── 1. Load today's bets ─────────────────────────────────────────────
    bets = []
    with open(tracker_path, 'r', newline='') as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if not header:
            print("\n  📭 Bet tracker is empty.")
            return
        hmap = {h.strip(): i for i, h in enumerate(header)}
        for row in reader:
            if not row or len(row) < 12:
                continue
            bets.append({
                'gid': row[hmap.get('ID', 0)].strip(),
                'away': row[hmap.get('Away', 2)].strip(),
                'home': row[hmap.get('Home', 3)].strip(),
                'fair_orig': float(row[hmap.get('Fair', 4)]) if row[hmap.get('Fair', 4)] else 0.0,
                'market_orig': float(row[hmap.get('Market', 5)]) if row[hmap.get('Market', 5)] else 0.0,
                'edge_orig': float(row[hmap.get('Edge', 6)]) if row[hmap.get('Edge', 6)] else 0.0,
                'pick': row[hmap.get('Pick', 11)].strip(),
                'timestamp': row[hmap.get('Timestamp', 1)].strip(),
            })

    if not bets:
        print("\n  📭 No valid bets found in today's tracker.")
        return

    # ── 2. Load current odds cache ───────────────────────────────────────
    odds_data = {}
    odds_fetch_time = None
    odds_path = os.path.join(base_dir, 'odds_cache.json')
    try:
        if os.path.exists(odds_path):
            with open(odds_path, 'r') as f:
                raw = json.load(f)
            odds_data = raw.get('games', {})
            for gdata in odds_data.values():
                fa = gdata.get('fetched_at', '')
                if fa:
                    try:
                        ts = datetime.fromisoformat(fa.replace('Z', '+00:00'))
                        if odds_fetch_time is None or ts > odds_fetch_time:
                            odds_fetch_time = ts
                    except ValueError:
                        pass
    except (IOError, json.JSONDecodeError):
        pass

    # Human-friendly odds timestamp
    odds_age_str = "unknown"
    if odds_fetch_time:
        try:
            local_ft = odds_fetch_time.astimezone().replace(tzinfo=None)
        except Exception:
            local_ft = odds_fetch_time.replace(tzinfo=None)
        mins_ago = (datetime.now() - local_ft).total_seconds() / 60
        if mins_ago < 60:
            odds_age_str = f"{int(mins_ago)}m ago"
        else:
            odds_age_str = f"{int(mins_ago // 60)}h {int(mins_ago % 60)}m ago"

    # ── 3. Load current injuries ─────────────────────────────────────────
    current_injuries = get_injuries()  # {team_full_name: [player_dicts]}

    # ── 4. Display review header ─────────────────────────────────────────
    print("\n" + "=" * 80)
    print(f"  🔍 PRE-TIPOFF REVIEW | {today.strftime('%B %d, %Y')}")
    print(f"  📊 Reviewing {len(bets)} placed bet{'s' if len(bets) != 1 else ''} against fresh data")
    print(f"  📈 Odds cache: {odds_age_str}")
    print("=" * 80)

    EDGE_CAP = load_edge_cap()
    action_summary = {'HOLD': 0, 'HEDGE': 0, 'REVIEW': 0}

    for bet in bets:
        away, home = bet['away'], bet['home']
        matchup_key = None
        # Build lookup keys that match odds_cache.json format ("Team @ Team")
        for key in odds_data:
            # odds_cache uses short names like "Pacers @ Wizards" or full names
            k_lower = key.lower()
            if (away.lower().split()[-1] in k_lower and home.lower().split()[-1] in k_lower):
                matchup_key = key
                break

        print(f"\n  {'─' * 72}")
        print(f"  {bet['gid']}  {away} @ {home}")
        print(f"  Bet: {bet['pick']} | Placed at {bet['timestamp']}")
        print(f"  {'─' * 72}")

        # ── Injury changes ───────────────────────────────────────────────
        away_inj = current_injuries.get(away, [])
        home_inj = current_injuries.get(home, [])
        out_players = []
        gtd_players = []
        for p in away_inj + home_inj:
            status = (p.get('status', '') or '').lower()
            team_short = away.split()[-1] if p in away_inj else home.split()[-1]
            label = f"{p['name']} ({team_short})"
            if 'out' in status:
                out_players.append(label)
            elif 'game time' in status or 'questionable' in status or 'doubtful' in status or 'day-to-day' in status:
                gtd_players.append(label)

        if out_players:
            print(f"  🚑 OUT: {', '.join(out_players)}")
        if gtd_players:
            print(f"  ⚠️  GTD/Q: {', '.join(gtd_players)}")
        if not out_players and not gtd_players:
            print(f"  ✅ Injuries: No significant changes")

        # ── Line movement ────────────────────────────────────────────────
        current_market = None
        if matchup_key and matchup_key in odds_data:
            try:
                current_market = float(odds_data[matchup_key].get('consensus_line', ''))
            except (ValueError, TypeError):
                pass

        line_moved = False
        if current_market is not None:
            movement = round(current_market - bet['market_orig'], 1)
            if abs(movement) >= 0.5:
                direction = "toward your pick ✅" if (
                    (bet['pick'] == home and movement < 0) or
                    (bet['pick'] == away and movement > 0) or
                    (bet['pick'] != home and bet['pick'] != away and False)
                ) else "against your pick ⚠️"
                print(f"  📉 Line moved: {bet['market_orig']} → {current_market} ({movement:+.1f}, {direction})")
                line_moved = True
            else:
                print(f"  📈 Line: {bet['market_orig']} → {current_market} (stable)")
        else:
            print(f"  📈 Line: {bet['market_orig']} (current market unavailable)")

        # ── Updated edge recalculation ───────────────────────────────────
        new_fair = None
        new_edge = None
        try:
            fair_result = predict_nba_spread(away, home)
            new_fair = fair_result[0]
            market_for_edge = current_market if current_market is not None else bet['market_orig']
            raw_new_edge = round(abs(new_fair - market_for_edge), 2)
            new_edge = min(raw_new_edge, EDGE_CAP)
            fair_change = round(new_fair - bet['fair_orig'], 1)

            print(f"  🧮 Fair line: {bet['fair_orig']} → {new_fair}"
                  f" ({fair_change:+.1f})" if abs(fair_change) >= 0.1 else
                  f"  🧮 Fair line: {new_fair} (unchanged)")
            print(f"  📐 Edge: {bet['edge_orig']} → {new_edge} pts"
                  f" (was {bet['edge_orig']}, now {new_edge})")
        except Exception as e:
            print(f"  🧮 Edge recalc failed: {e}")

        # ── Action suggestion ────────────────────────────────────────────
        action = "HOLD"
        reason = ""

        if new_edge is not None:
            edge_delta = new_edge - bet['edge_orig']

            if new_edge >= bet['edge_orig']:
                action = "HOLD"
                reason = "Edge improved or stable"
                if new_edge > bet['edge_orig'] + 1:
                    reason = f"Edge grew +{edge_delta:.1f} pts — consider adding"
            elif new_edge >= 1.0:
                action = "HOLD"
                reason = f"Edge narrowed to {new_edge} but still positive"
            elif new_edge < 1.0 and out_players:
                action = "HEDGE"
                reason = f"Edge collapsed to {new_edge} + key player(s) OUT"
            elif new_edge < 1.0:
                action = "REVIEW"
                reason = f"Edge < 1 pt ({new_edge}) — thin margin"

            # Override: major injury to betted team's key player
            betted_team_inj = home_inj if bet['pick'] == home else away_inj
            major_outs = [p for p in betted_team_inj if 'out' in (p.get('status', '') or '').lower()]
            if major_outs and new_edge < bet['edge_orig']:
                if action != "HEDGE":
                    action = "REVIEW"
                    reason = f"Key player OUT on {bet['pick']}: {major_outs[0]['name']}"
        else:
            action = "HOLD"
            reason = "Unable to recalculate — no data change detected"

        # Action display
        action_icons = {'HOLD': '🟢', 'HEDGE': '🔴', 'REVIEW': '🟡'}
        icon = action_icons.get(action, '⚪')
        print(f"\n  {icon} ACTION: {action}")
        print(f"     {reason}")
        action_summary[action] = action_summary.get(action, 0) + 1

    # ── Overall summary ──────────────────────────────────────────────────
    print(f"\n{'=' * 80}")
    holds = action_summary.get('HOLD', 0)
    hedges = action_summary.get('HEDGE', 0)
    reviews = action_summary.get('REVIEW', 0)
    print(f"  📋 SUMMARY: {holds} HOLD | {reviews} REVIEW | {hedges} HEDGE/CASH OUT")
    if hedges:
        print(f"  🔴 {hedges} bet{'s' if hedges != 1 else ''} flagged for hedging — check injury/line details above")
    if reviews:
        print(f"  🟡 {reviews} bet{'s' if reviews != 1 else ''} need manual review — edge is thin or situation changed")
    if holds == len(bets):
        print(f"  🟢 All bets look solid — no action needed before tip-off")
    print(f"{'=' * 80}")


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

            # ── Load today's bets & odds cache for dashboard status ──
            bets_placed = set()  # set of GIDs that have bets logged
            bet_tracker_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                            f"bet_tracker_{today.isoformat()}.csv")
            if os.path.exists(bet_tracker_path):
                try:
                    with open(bet_tracker_path, 'r', newline='') as bf:
                        reader = csv.reader(bf)
                        header = next(reader, None)
                        for row in reader:
                            if row:
                                bets_placed.add(row[0].strip().upper())
                except (IOError, StopIteration):
                    pass

            odds_cache_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'odds_cache.json')
            odds_fetch_time = None   # most recent odds fetch as local datetime
            try:
                if os.path.exists(odds_cache_path):
                    with open(odds_cache_path, 'r') as of:
                        odds_data = json.load(of)
                    # Find the most recent fetched_at timestamp across all cached games
                    for gdata in odds_data.get('games', {}).values():
                        fa = gdata.get('fetched_at', '')
                        if fa:
                            try:
                                ts = datetime.fromisoformat(fa.replace('Z', '+00:00'))
                                if odds_fetch_time is None or ts > odds_fetch_time:
                                    odds_fetch_time = ts
                            except ValueError:
                                pass
            except (IOError, json.JSONDecodeError, KeyError):
                pass

            if games:
                if source:
                    print(f"📡 Source: {source}")

                # ── Group games into tip-off windows ──
                game_windows = {}  # time_str → [list of GIDs]
                for i, (away, home, status) in enumerate(games):
                    gid = f"G{i+1}"
                    schedule[gid] = (away, home)
                    raw_time = status.strip()
                    # Detect valid time format vs in-progress / empty status
                    _is_time = bool(raw_time and re.match(r'\d{1,2}:\d{2}\s*(?:AM|PM)', raw_time, re.IGNORECASE))
                    if _is_time:
                        time_str = raw_time
                    elif raw_time:
                        time_str = raw_time          # ESPN status text (e.g. score)
                    else:
                        time_str = "\u23f3 Live"     # Empty = in-progress (ESPN replaced time with score)
                    game_windows.setdefault(time_str, []).append(gid)
                    bet_tag = " 🎫" if gid in bets_placed else ""
                    print(f"{gid:<4} {away:<24} @ {home:<24} {time_str}{bet_tag}")

                # ── Legend ──
                if bets_placed:
                    bet_count = sum(1 for g in schedule if g in bets_placed)
                    total_games = len(schedule)
                    print(f"  🎫 = Bet placed ({bet_count}/{total_games} games)")

                # ── Per-window CLV & injury fetch schedule ──
                print("")
                now = datetime.now()
                has_any_upcoming = False

                # Parse each window's tip-off as a datetime for comparison
                window_infos = []  # (tip_datetime, time_str, gids)
                for time_str, gids in game_windows.items():
                    tip_dt = None
                    if time_str != "TBD":
                        try:
                            tip_dt = datetime.combine(today, datetime.strptime(time_str, "%I:%M %p").time())
                        except ValueError:
                            pass
                    window_infos.append((tip_dt, time_str, gids))
                # Sort by tip-off time (TBD last)
                window_infos.sort(key=lambda x: x[0] or datetime.max)

                for tip_dt, time_str, gids in window_infos:
                    gid_label = ", ".join(gids)
                    if tip_dt is None:
                        if "\u23f3" in time_str or time_str == "\u23f3 Live":
                            # In-progress games — no CLV action needed
                            print(f"  📈 {time_str} ({gid_label}): CLV locked (in progress)")
                        else:
                            print(f"  📈 {time_str} ({gid_label}): ⚠️  Tip-off TBD — fetch odds & injuries once time is set")
                        continue

                    fetch_target = tip_dt - timedelta(minutes=15)
                    fetch_time_str = fetch_target.strftime("%-I:%M %p")

                    # Determine if odds are fresh for THIS window (fetched within 30 min of tip)
                    odds_status = "❌ Not fetched"
                    if odds_fetch_time:
                        # Convert odds_fetch_time to local naive for comparison
                        try:
                            local_fetch = odds_fetch_time.astimezone().replace(tzinfo=None)
                        except Exception:
                            local_fetch = odds_fetch_time.replace(tzinfo=None)
                        mins_before_tip = (tip_dt - local_fetch).total_seconds() / 60
                        if 0 <= mins_before_tip <= 30:
                            odds_status = "✅ Fresh"
                        elif mins_before_tip < 0:
                            # Fetched after tip-off
                            odds_status = "✅ Fetched post-tip"
                        else:
                            hours_ago = (now - local_fetch).total_seconds() / 3600
                            if hours_ago < 1:
                                odds_status = f"⚠️  Fetched {int(hours_ago * 60)}m ago"
                            else:
                                odds_status = f"⚠️  Fetched {int(hours_ago)}h ago"

                    if now < tip_dt:
                        has_any_upcoming = True
                        print(f"  📈 {time_str} ({gid_label}): CLV {odds_status}")
                        if not odds_status.startswith("✅"):
                            print(f"     → Run at ~{fetch_time_str}: ./fetch_all_nba_data.sh odds,injuries")
                    else:
                        # Game already tipped off
                        print(f"  📈 {time_str} ({gid_label}): CLV {odds_status} (in progress)")

                if not has_any_upcoming and odds_fetch_time:
                    print(f"  📈 All games in progress or finished")
            else:
                print("📅 No games scheduled today (All-Star break or off day).")
                print("💡 TIP: Type 'U' to view upcoming games, or 'C' for a custom matchup.")

            print("-" * 75)
            print("COMMANDS: [G#] (Analyze) | [P] (Pre-Tip Review) | [B] (Bets) | [V] (Validate) | [U] (Upcoming) | [R] (Refresh) | [C] (Custom) | [Q] (Quit)")
            choice = input("Enter Command: ").upper()

            if choice == 'Q':
                print("Shutting down. Happy Betting!")
                break

            elif choice == 'B':
                display_bet_tracker()
                continue

            elif choice == 'P':
                display_pretipoff_review()
                continue

            elif choice == 'V':
                validate_historical_bets()
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
                # ── Upcoming Games (next 7 days) — loops until user exits ──
                while True:
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
                        break
                    else:
                        # Merge upcoming into schedule so user can analyze them
                        schedule.update(upcoming_schedule)
                        print(f"\n  💡 Total: {game_counter} games over the next 7 days")
                        print(f"  💡 Type a game ID (e.g., U1) to analyze any upcoming matchup.")

                    print("=" * 75)
                    print("  Q. Back to main menu")
                    print("-" * 75)
                    u_choice = input("Enter U# to analyze (or Q to go back): ").upper().strip()

                    if not u_choice or u_choice == 'Q':
                        break

                    if u_choice not in schedule:
                        print("❌ Command not recognized.")
                        continue

                    # Inline analysis for the selected upcoming game
                    u_away, u_home = schedule[u_choice]
                    print(f"\n[PREVIEW] {u_away} vs {u_home} (upcoming game — research mode)")
                    try:
                        line_in = input(f"Market Line for {u_home} (e.g., -5.5): ").strip()
                        if not line_in:
                            print("❌ No market line entered. Returning to upcoming list.")
                            continue
                        try:
                            market = float(line_in)
                        except ValueError:
                            print(f"❌ Invalid market line '{line_in}'. Must be a number (e.g., -5.5).")
                            continue

                        fair_line, q_players, news, flag, star_tax_failed = predict_nba_spread(u_away, u_home)
                        raw_edge = round(abs(fair_line - market), 2)
                        EDGE_CAP = load_edge_cap()
                        edge = min(raw_edge, EDGE_CAP)
                        edge_capped = raw_edge > EDGE_CAP
                        kelly = calculate_kelly(market, fair_line)

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

                        recommendation = u_home if fair_line < market else u_away
                        if edge_capped:
                            print(f"🚨 REVIEW REQUIRED: {recommendation} (edge capped at {EDGE_CAP} — verify before betting)")
                        elif edge >= 5 and "HIGH" in conf:
                            print(f"🔥 STRONG SIGNAL: Bet {recommendation}")
                        elif edge >= 3:
                            print(f"📊 LEAN: {recommendation} (moderate edge)")
                        else:
                            print(f"📉 LOW EDGE: {recommendation} (thin margin — proceed with caution)")

                        print("\n  📋 PREVIEW ONLY — This is an upcoming game.")
                        print("     Data may change by game day (injuries, lines, rest).")
                        print("     Re-analyze on game day to log a bet.")
                    except Exception as e:
                        print(f"❌ Error during analysis: {e}")
                # done with U loop
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
