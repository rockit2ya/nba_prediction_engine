#!/usr/bin/env python3
"""
post_mortem.py — NBA Prediction Engine Performance Analyzer

Provides single-day post-mortems and lifetime performance dashboards
to determine whether the prediction model is pro-level.

Pro Benchmark: > 52.4% ATS win rate (break-even at -110 vig)

Usage:
    python post_mortem.py
"""

import pandas as pd
import glob
import os
import re
from datetime import datetime

# ─── Constants ────────────────────────────────────────────────────────────────
BREAKEVEN_RATE = 0.524          # ATS break-even at -110 odds
VIG = -110                      # Standard juice
HIGH_SIGNAL_EDGE = 5            # Minimum edge for "high-signal" bets
EDGE_TIERS = [(5, 10), (10, 15), (15, float('inf'))]
EDGE_TIER_LABELS = ['5–10', '10–15', '15+']

INJURY_FILE = "nba_injuries.csv"

# Common nickname aliases for robust matching
TEAM_ALIASES = {
    'blazers': 'trail blazers',
    'sixers': '76ers',
    'wolves': 'timberwolves',
}

def names_match(a, b):
    """Case-insensitive team name match with alias support."""
    a_low = a.strip().lower()
    b_low = b.strip().lower()
    if a_low == b_low:
        return True
    a_resolved = TEAM_ALIASES.get(a_low, a_low)
    b_resolved = TEAM_ALIASES.get(b_low, b_low)
    return a_resolved == b_resolved


# ═══════════════════════════════════════════════════════════════════════════════
#  DATA LOADING & HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def load_all_trackers():
    """Load and combine all bet_tracker_*.csv files into one DataFrame."""
    pattern = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bet_tracker_*.csv')
    files = sorted(glob.glob(pattern))
    if not files:
        return pd.DataFrame()

    frames = []
    for f in files:
        df = pd.read_csv(f)
        # Extract date from filename
        match = re.search(r'bet_tracker_(\d{4}-\d{2}-\d{2})\.csv', f)
        if match:
            df['Date'] = match.group(1)
        frames.append(df)

    combined = pd.concat(frames, ignore_index=True)
    # Normalize Result column
    combined['Result'] = combined['Result'].astype(str).str.strip().str.upper()
    # Drop exact duplicate rows (same game logged twice)
    combined = combined.drop_duplicates(subset=['Date', 'Away', 'Home', 'Pick'], keep='first')
    return combined


def load_tracker(date_str):
    """Load a single date's bet tracker."""
    filename = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"bet_tracker_{date_str}.csv")
    if not os.path.exists(filename):
        return None
    df = pd.read_csv(filename)
    df['Result'] = df['Result'].astype(str).str.strip().str.upper()
    df['Date'] = date_str
    df = df.drop_duplicates(subset=['Away', 'Home', 'Pick'], keep='first')
    return df


def load_injuries():
    """Load injury data if available."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), INJURY_FILE)
    if os.path.exists(path):
        return pd.read_csv(path, comment='#')
    return None


def parse_margin(row):
    """Extract win/loss margin from Notes column. Returns margin from pick's perspective."""
    notes = str(row.get('Notes', ''))
    m = re.search(r'Final Score: (.+?) (\d+) - (.+?) (\d+)', notes)
    if not m:
        return None
    team1, score1, team2, score2 = m.groups()
    team1, team2 = team1.strip(), team2.strip()
    score1, score2 = int(score1), int(score2)
    pick = str(row['Pick']).strip()
    home = str(row['Home']).strip()
    away = str(row['Away']).strip()
    # Determine which score belongs to the picked team (alias-aware matching)
    if names_match(pick, home):
        return score2 - score1 if names_match(team1, away) or not names_match(team1, home) else score1 - score2
    else:
        return score1 - score2 if names_match(team1, away) or not names_match(team1, home) else score2 - score1


def calc_units(row):
    """
    Calculate units won/lost for a bet at -110 odds.
    WIN  = +1.0 unit profit (risking 1.1 to win 1.0)
    LOSS = -1.1 units (the amount risked)
    PUSH = 0.0 units (money returned)
    """
    if row['Result'] == 'WIN':
        return 1.0
    elif row['Result'] == 'LOSS':
        return -1.1
    return 0.0


def calc_real_dollars(row):
    """
    Calculate real dollar P/L from Bet, Odds, and Result columns.
    Returns None if bet tracking data is not available.
    """
    try:
        bet = float(str(row.get('Bet', '')).replace('$', '').replace(',', '').strip())
        odds = int(str(row.get('Odds', '')).replace('+', '').strip())
    except (ValueError, TypeError):
        return None
    if bet <= 0:
        return None
    if row['Result'] == 'WIN':
        if odds > 0:
            return round(bet * (odds / 100), 2)
        else:
            return round(bet * (100 / abs(odds)), 2)
    elif row['Result'] == 'LOSS':
        return round(-bet, 2)
    elif row['Result'] == 'PUSH':
        return 0.0
    return None


def has_bet_data(df):
    """Check if the DataFrame has real dollar bet tracking data."""
    if 'Bet' not in df.columns or 'Odds' not in df.columns:
        return False
    valid = df['Bet'].apply(lambda x: str(x).replace('$','').replace(',','').strip() not in ('', 'nan', '0'))
    return valid.any()


def calc_kelly_units(row):
    """
    Calculate units won/lost scaled by Kelly % suggestion.
    Uses the Kelly column as the fraction of bankroll risked.
    """
    kelly_str = str(row.get('Kelly', '0%')).replace('%', '')
    try:
        kelly_frac = float(kelly_str) / 100.0
    except ValueError:
        kelly_frac = 0.0

    if row['Result'] == 'WIN':
        return kelly_frac * (100 / abs(VIG))  # profit on a kelly-sized bet
    elif row['Result'] == 'LOSS':
        return -kelly_frac * 1.0  # lost the kelly-sized stake
    return 0.0


def filter_completed(df):
    """Return only WIN/LOSS/PUSH rows (exclude PENDING)."""
    return df[df['Result'].isin(['WIN', 'LOSS', 'PUSH'])].copy()


def filter_high_signal(df):
    """Return only high-signal bets (Edge >= threshold)."""
    df = df.copy()
    df['Edge'] = pd.to_numeric(df['Edge'], errors='coerce').fillna(0)
    return df[df['Edge'] >= HIGH_SIGNAL_EDGE].copy()


# ═══════════════════════════════════════════════════════════════════════════════
#  DISPLAY HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def header(title, width=65):
    print(f"\n{'=' * width}")
    print(f"  {title}")
    print(f"{'=' * width}")


def section(title, width=65):
    print(f"\n{'─' * width}")
    print(f"  {title}")
    print(f"{'─' * width}")


def grade_win_rate(rate, n):
    """Assign a letter grade to win rate performance."""
    if n < 10:
        return "📊 (Sample too small — need 10+ bets)"
    if rate >= 0.60:
        return "🅰️  ELITE"
    elif rate >= 0.55:
        return "🅱️  PRO-LEVEL"
    elif rate >= BREAKEVEN_RATE:
        return "🆗  PROFITABLE"
    elif rate >= 0.50:
        return "⚠️  BELOW BREAKEVEN (losing to vig)"
    else:
        return "🔴 LOSING RECORD"


# ═══════════════════════════════════════════════════════════════════════════════
#  1. SINGLE-DAY POST-MORTEM
# ═══════════════════════════════════════════════════════════════════════════════

def daily_post_mortem(date_str):
    """Analyze a single day's bet tracker with loss/win pattern analysis."""
    df = load_tracker(date_str)
    if df is None:
        print(f"  ❌ File not found: bet_tracker_{date_str}.csv")
        return

    completed = filter_completed(df)
    high = filter_high_signal(completed)
    all_wins = completed[completed['Result'] == 'WIN']
    all_losses = completed[completed['Result'] == 'LOSS']
    pending = df[df['Result'] == 'PENDING']

    header(f"📅 Daily Post-Mortem: {date_str}")

    # Overall day stats
    print(f"\n  Total bets logged:    {len(df)}")
    print(f"  Completed:            {len(completed)}  (Pending: {len(pending)})")
    print(f"  Wins: {len(all_wins)} | Losses: {len(all_losses)}")

    if len(completed) > 0:
        day_rate = len(all_wins) / len(completed)
        day_units = completed.apply(calc_units, axis=1).sum()
        print(f"  Win Rate (all bets):  {day_rate:.1%}")
        print(f"  Day P/L:              {day_units:+.1f} units")

        # Real dollar P/L if available
        if has_bet_data(completed):
            completed_copy = completed.copy()
            completed_copy['RealPL'] = completed_copy.apply(calc_real_dollars, axis=1)
            tracked = completed_copy.dropna(subset=['RealPL'])
            if not tracked.empty:
                day_pl = tracked['RealPL'].sum()
                day_wagered = tracked['Bet'].apply(lambda x: float(str(x).replace('$','').replace(',','').strip())).sum()
                print(f"  Day P/L (real $):     ${day_pl:+,.2f}  (wagered: ${day_wagered:,.2f})")

    # High-signal breakdown
    if not high.empty:
        hw = high[high['Result'] == 'WIN']
        hl = high[high['Result'] == 'LOSS']
        section("High-Signal Bets (Edge ≥ 5)")
        print(f"  Count: {len(high)}  |  Wins: {len(hw)}  |  Losses: {len(hl)}")
        if len(high) > 0:
            print(f"  Win Rate: {len(hw)/len(high):.1%}")

    # Loss analysis
    injuries = load_injuries()
    if not all_losses.empty:
        section("Loss Analysis")
        loss_margins = []
        injury_count = 0
        low_edge_count = 0

        for _, row in all_losses.iterrows():
            margin = parse_margin(row)
            notes = str(row.get('Notes', ''))
            print(f"  ❌ {row['Away']} @ {row['Home']} | Pick: {row['Pick']} | Edge: {row['Edge']}")
            if margin is not None:
                print(f"     Margin: {margin}  |  {notes}")
                loss_margins.append(margin)

            # Injury check (exact match, not substring)
            if injuries is not None:
                team_inj = injuries[injuries['team'].str.strip().str.lower() == str(row['Pick']).strip().lower()]
                if not team_inj.empty:
                    injury_count += 1
                    for _, inj in team_inj.iterrows():
                        print(f"     🏥 {inj['player']} ({inj['position']}) — {inj['injury']} [{inj['status']}]")

            try:
                edge_val = float(row['Edge'])
            except (ValueError, TypeError):
                edge_val = 0.0
            if edge_val < 10:
                low_edge_count += 1

        print(f"\n  Losses with injury impact:  {injury_count}")
        print(f"  Losses with low edge (<10): {low_edge_count}")
        if loss_margins:
            print(f"  Avg margin of defeat:       {sum(loss_margins)/len(loss_margins):.1f}")

    # Win analysis
    if not all_wins.empty:
        section("Win Analysis")
        win_margins = []
        for _, row in all_wins.iterrows():
            margin = parse_margin(row)
            notes = str(row.get('Notes', ''))
            print(f"  ✅ {row['Away']} @ {row['Home']} | Pick: {row['Pick']} | Edge: {row['Edge']}")
            if margin is not None:
                print(f"     Margin: {margin:+d}  |  {notes}")
                win_margins.append(margin)
        if win_margins:
            print(f"\n  Avg margin of victory: {sum(win_margins)/len(win_margins):+.1f}")


# ═══════════════════════════════════════════════════════════════════════════════
#  2. LIFETIME PERFORMANCE DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════

def lifetime_dashboard():
    """Aggregate all-time performance across all bet trackers."""
    df = load_all_trackers()
    if df.empty:
        print("  ❌ No bet tracker files found.")
        return

    completed = filter_completed(df)
    if completed.empty:
        print("  ❌ No completed bets found (all PENDING).")
        return

    wins = completed[completed['Result'] == 'WIN']
    losses = completed[completed['Result'] == 'LOSS']
    pending = df[df['Result'] == 'PENDING']
    dates = sorted(completed['Date'].unique())

    header("🏆 LIFETIME PERFORMANCE DASHBOARD")

    # ── Overview ──
    section("Overview")
    total = len(completed)
    win_rate = len(wins) / total
    total_units = completed.apply(calc_units, axis=1).sum()
    roi = (total_units / (total * 1.1)) * 100  # ROI = profit / total risked

    print(f"  Date Range:      {dates[0]} → {dates[-1]}  ({len(dates)} day(s))")
    print(f"  Total Bets:      {len(df)}  (Completed: {total}, Pending: {len(pending)})")
    print(f"  Record:          {len(wins)}W - {len(losses)}L")
    print(f"  Win Rate:        {win_rate:.1%}  (Break-even: {BREAKEVEN_RATE:.1%})")
    print(f"  Grade:           {grade_win_rate(win_rate, total)}")
    kelly_units = completed.apply(calc_kelly_units, axis=1).sum()
    print(f"  Total P/L:       {total_units:+.1f} units  (Kelly-sized: {kelly_units:+.2f} units)")
    print(f"  ROI:             {roi:+.1f}%")

    # ── Real Dollar P/L (if bet data available) ──
    if has_bet_data(completed):
        completed_copy = completed.copy()
        completed_copy['RealPL'] = completed_copy.apply(calc_real_dollars, axis=1)
        tracked = completed_copy.dropna(subset=['RealPL'])
        if not tracked.empty:
            total_wagered = tracked['Bet'].apply(lambda x: float(str(x).replace('$','').replace(',','').strip())).sum()
            total_pl = tracked['RealPL'].sum()
            real_roi = (total_pl / total_wagered * 100) if total_wagered > 0 else 0
            section("💰 Real Money P/L")
            print(f"  Tracked Bets:    {len(tracked)} of {total} completed")
            print(f"  Total Wagered:   ${total_wagered:,.2f}")
            print(f"  Net P/L:         ${total_pl:+,.2f}")
            print(f"  ROI:             {real_roi:+.1f}%")

            # Book-level breakdown
            if 'Book' in tracked.columns:
                books = tracked.copy()
                books['Book'] = books['Book'].astype(str).str.strip()
                books = books[books['Book'].isin(['', 'nan']) == False]
                if not books.empty:
                    print(f"\n  {'Sportsbook':<18} {'Bets':<6} {'Record':<10} {'P/L':<12} {'Win%'}")
                    print(f"  {'─'*18} {'─'*6} {'─'*10} {'─'*12} {'─'*6}")
                    for book_name, grp in books.groupby('Book'):
                        bw = (grp['Result'] == 'WIN').sum()
                        bl = (grp['Result'] == 'LOSS').sum()
                        bpl = grp['RealPL'].sum()
                        bwr = bw / len(grp) if len(grp) > 0 else 0
                        print(f"  {book_name:<18} {len(grp):<6} {bw}W-{bl}L{'':<4} ${bpl:>+9,.2f}  {bwr:.0%}")

    # ── High-Signal Only ──
    high = filter_high_signal(completed)
    if not high.empty:
        hw = high[high['Result'] == 'WIN']
        hl = high[high['Result'] == 'LOSS']
        high_rate = len(hw) / len(high)
        high_units = high.apply(calc_units, axis=1).sum()
        high_roi = (high_units / (len(high) * 1.1)) * 100

        high_kelly = high.apply(calc_kelly_units, axis=1).sum()
        section("High-Signal Bets (Edge ≥ 5)")
        print(f"  Record:          {len(hw)}W - {len(hl)}L")
        print(f"  Win Rate:        {high_rate:.1%}")
        print(f"  Grade:           {grade_win_rate(high_rate, len(high))}")
        print(f"  P/L:             {high_units:+.1f} units  (Kelly-sized: {high_kelly:+.2f} units)")
        print(f"  ROI:             {high_roi:+.1f}%")

    # ── Edge Calibration ──
    section("Edge Calibration (do bigger edges win more?)")
    print(f"  {'Tier':<10} {'Record':<12} {'Win Rate':<12} {'P/L':<10} {'Verdict'}")
    print(f"  {'─'*10} {'─'*12} {'─'*12} {'─'*10} {'─'*15}")

    calibration_ok = True
    prev_rate = None  # None means no previous tier with data yet
    tier_rates = []   # collect (label, rate, n) for all non-empty tiers
    for (lo, hi_bound), label in zip(EDGE_TIERS, EDGE_TIER_LABELS):
        tier = completed[(completed['Edge'] >= lo) & (completed['Edge'] < hi_bound)]
        if tier.empty:
            print(f"  {label:<10} {'—':<12} {'—':<12} {'—':<10} No data")
            continue
        tw = tier[tier['Result'] == 'WIN']
        tl = tier[tier['Result'] == 'LOSS']
        tr = len(tw) / len(tier) if len(tier) > 0 else 0
        tu = tier.apply(calc_units, axis=1).sum()
        tier_rates.append((label, tr, len(tier)))

        verdict = "✅" if tr >= BREAKEVEN_RATE else "⚠️"
        # Check inversion: if this tier's rate is lower than ANY previous tier
        if prev_rate is not None and tr < prev_rate:
            verdict = "🔻 Inverted"
            calibration_ok = False

        print(f"  {label:<10} {f'{len(tw)}W-{len(tl)}L':<12} {tr:.1%}{'':<7} {tu:+.1f}{'':<5} {verdict}")
        prev_rate = tr  # track last non-empty tier rate

    if calibration_ok and len(tier_rates) >= 2:
        print("\n  ✅ Calibration: Higher edges are winning at higher rates — model is well-calibrated.")
    elif calibration_ok:
        print("\n  ⚠️  Calibration: Not enough tier data to fully assess (need 2+ tiers with bets).")
    else:
        print("\n  ⚠️  Calibration issue: A lower-edge tier is outperforming a higher one.")
        print("     This may indicate the model overestimates large edges, or sample size is too small.")

    # ── Streak & Drawdown ──
    section("Streaks & Drawdown")
    results_seq = completed.sort_values('Date').apply(calc_units, axis=1).tolist()
    result_labels = completed.sort_values('Date')['Result'].tolist()

    # Current streak
    if result_labels:
        current = result_labels[-1]
        streak = 0
        for r in reversed(result_labels):
            if r == current:
                streak += 1
            else:
                break
        streak_icon = '🔥' if current == 'WIN' else '🧊'
        print(f"  Current Streak:     {streak_icon} {streak} {current}{'S' if streak > 1 else ''}")

    # Max win/loss streaks
    max_w_streak = max_l_streak = cur_w = cur_l = 0
    for r in result_labels:
        if r == 'WIN':
            cur_w += 1
            cur_l = 0
        else:
            cur_l += 1
            cur_w = 0
        max_w_streak = max(max_w_streak, cur_w)
        max_l_streak = max(max_l_streak, cur_l)
    print(f"  Best Win Streak:    {max_w_streak}")
    print(f"  Worst Loss Streak:  {max_l_streak}")

    # Max drawdown (cumulative units)
    cumulative = []
    running = 0
    for u in results_seq:
        running += u
        cumulative.append(running)
    if cumulative:
        peak = cumulative[0]
        max_dd = 0
        for val in cumulative:
            if val > peak:
                peak = val
            dd = peak - val
            if dd > max_dd:
                max_dd = dd
        print(f"  Max Drawdown:       {max_dd:.1f} units")
        print(f"  Current Balance:    {cumulative[-1]:+.1f} units")

    # ── Daily Trend ──
    section("Daily Trend")
    daily = completed.groupby('Date').agg(
        W=('Result', lambda x: (x == 'WIN').sum()),
        L=('Result', lambda x: (x == 'LOSS').sum()),
        Bets=('Result', 'count'),
        AvgEdge=('Edge', 'mean')
    ).reset_index()
    daily['WinRate'] = daily['W'] / daily['Bets']
    daily['Units'] = daily.apply(lambda r: r['W'] * 1.0 + r['L'] * -1.1, axis=1)
    daily['CumUnits'] = daily['Units'].cumsum()

    show_dollars = has_bet_data(completed)
    if show_dollars:
        def _day_pl(date):
            day_df = completed[completed['Date'] == date].copy()
            day_df['RealPL'] = day_df.apply(calc_real_dollars, axis=1)
            t = day_df.dropna(subset=['RealPL'])
            return t['RealPL'].sum() if not t.empty else 0.0
        daily['$P/L'] = daily['Date'].apply(_day_pl)

    dollar_hdr = '  $P/L' if show_dollars else ''
    print(f"  {'Date':<12} {'Record':<10} {'Rate':<8} {'P/L':<8} {'Cum P/L':<10} {'AvgEdge':<8}{dollar_hdr}")
    print(f"  {'─'*12} {'─'*10} {'─'*8} {'─'*8} {'─'*10} {'─'*8}{'  ' + '─'*8 if show_dollars else ''}")
    for _, row in daily.iterrows():
        rec = f"{int(row['W'])}W-{int(row['L'])}L"
        dollar_val = f"  ${row['$P/L']:>+8,.2f}" if show_dollars else ''
        print(f"  {row['Date']:<12} {rec:<10} {row['WinRate']:.0%}{'':<5} {row['Units']:+.1f}{'':<4} {row['CumUnits']:+.1f}{'':<6} {row['AvgEdge']:.1f}{dollar_val}")

    # ── Pro Verdict ──
    section("🏁 PRO-LEVEL VERDICT")
    checks = []

    # Check 1: Win rate
    if win_rate >= BREAKEVEN_RATE:
        checks.append(("ATS Win Rate > 52.4%", True, f"{win_rate:.1%}"))
    else:
        checks.append(("ATS Win Rate > 52.4%", False, f"{win_rate:.1%}"))

    # Check 2: Positive ROI
    checks.append(("Positive ROI", roi > 0, f"{roi:+.1f}%"))

    # Check 3: High-signal win rate
    if not high.empty:
        high_wr = len(hw) / len(high)
        checks.append(("High-Signal Win Rate > 55%", high_wr >= 0.55, f"{high_wr:.1%}"))

    # Check 4: Edge calibration
    checks.append(("Edge Calibration (higher edges win more)", calibration_ok, ""))

    # Check 5: Sample size
    checks.append(("Sufficient Sample (20+ bets)", total >= 20, f"n={total}"))

    passed = sum(1 for _, ok, _ in checks if ok)
    for label, ok, val in checks:
        icon = '✅' if ok else '❌'
        suffix = f"  ({val})" if val else ""
        print(f"  {icon} {label}{suffix}")

    print(f"\n  Score: {passed}/{len(checks)} checks passed")
    if passed == len(checks):
        print("  🏆 VERDICT: Model is performing at PRO level!")
    elif passed >= len(checks) - 1:
        print("  📈 VERDICT: Model is near pro-level — close to breaking through.")
    elif win_rate >= 0.50:
        print("  ⚠️  VERDICT: Model is above .500 but not yet profitable after vig.")
    else:
        print("  🔴 VERDICT: Model needs improvement — review edge calibration and loss patterns.")


# ═══════════════════════════════════════════════════════════════════════════════
#  3. EDGE CALIBRATION REPORT
# ═══════════════════════════════════════════════════════════════════════════════

def edge_calibration_report():
    """Detailed breakdown of model accuracy by edge size."""
    df = load_all_trackers()
    completed = filter_completed(df)

    if completed.empty:
        print("  ❌ No completed bets to analyze.")
        return

    header("📐 Edge Calibration Report")

    # Fine-grained edge buckets
    buckets = [(0, 3), (3, 5), (5, 8), (8, 10), (10, 15), (15, 20), (20, float('inf'))]
    bucket_labels = ['0–3', '3–5', '5–8', '8–10', '10–15', '15–20', '20+']

    print(f"\n  {'Edge':<10} {'Bets':<8} {'Record':<12} {'Win Rate':<12} {'P/L':<10} {'Avg Margin'}")
    print(f"  {'─'*10} {'─'*8} {'─'*12} {'─'*12} {'─'*10} {'─'*12}")

    for (lo, hi_bound), label in zip(buckets, bucket_labels):
        tier = completed[(completed['Edge'] >= lo) & (completed['Edge'] < hi_bound)]
        if tier.empty:
            print(f"  {label:<10} {'0':<8} {'—':<12} {'—':<12} {'—':<10} {'—'}")
            continue

        tw = tier[tier['Result'] == 'WIN']
        tl = tier[tier['Result'] == 'LOSS']
        tr = len(tw) / len(tier)
        tu = tier.apply(calc_units, axis=1).sum()

        margins = [m for m in (parse_margin(row) for _, row in tier.iterrows()) if m is not None]
        avg_m = f"{sum(margins)/len(margins):+.1f}" if margins else "—"

        bar = '█' * int(tr * 20) + '░' * (20 - int(tr * 20))
        print(f"  {label:<10} {len(tier):<8} {f'{len(tw)}W-{len(tl)}L':<12} {tr:.1%} {bar} {tu:+.1f}{'':<5} {avg_m}")

    # Correlation check
    section("Edge vs. Win Rate Correlation")
    completed_with_margin = completed.copy()
    completed_with_margin['won'] = (completed_with_margin['Result'] == 'WIN').astype(int)
    try:
        corr = completed_with_margin[['Edge', 'won']].corr().loc['Edge', 'won']
        if corr > 0.15:
            print(f"  Correlation: {corr:.3f} — ✅ Positive correlation (model edge is predictive)")
        elif corr > 0:
            print(f"  Correlation: {corr:.3f} — ⚠️  Weak positive correlation (edge is slightly predictive)")
        else:
            print(f"  Correlation: {corr:.3f} — 🔴 No correlation (edge may not be predictive)")
    except Exception:
        print("  Insufficient data to calculate correlation.")


# ═══════════════════════════════════════════════════════════════════════════════
#  4. DAILY TREND / PROFIT CURVE
# ═══════════════════════════════════════════════════════════════════════════════

def daily_trend():
    """Day-by-day P/L trend with rolling win rate and ASCII profit curve."""
    df = load_all_trackers()
    completed = filter_completed(df)

    if completed.empty:
        print("  ❌ No completed bets to analyze.")
        return

    header("📈 Daily Trend & Profit Curve")

    daily = completed.groupby('Date').agg(
        W=('Result', lambda x: (x == 'WIN').sum()),
        L=('Result', lambda x: (x == 'LOSS').sum()),
        Bets=('Result', 'count'),
        AvgEdge=('Edge', 'mean')
    ).reset_index().sort_values('Date')
    daily['Units'] = daily.apply(lambda r: r['W'] * 1.0 + r['L'] * -1.1, axis=1)
    daily['CumUnits'] = daily['Units'].cumsum()
    daily['CumW'] = daily['W'].cumsum()
    daily['CumBets'] = daily['Bets'].cumsum()
    daily['RollingRate'] = daily['CumW'] / daily['CumBets']

    # Real dollar P/L per day if available
    show_dollars = has_bet_data(completed)
    if show_dollars:
        def day_real_pl(date):
            day_df = completed[completed['Date'] == date].copy()
            day_df['RealPL'] = day_df.apply(calc_real_dollars, axis=1)
            tracked = day_df.dropna(subset=['RealPL'])
            return tracked['RealPL'].sum() if not tracked.empty else 0.0
        daily['DollarPL'] = daily['Date'].apply(day_real_pl)
        daily['CumDollarPL'] = daily['DollarPL'].cumsum()

    dollar_cols = '  Dollar P/L' if show_dollars else ''
    print(f"\n  {'Date':<12} {'Record':<10} {'Day P/L':<9} {'Cum P/L':<10} {'Cum Rate':<10} {'Trend':<8}{dollar_cols}")
    print(f"  {'─'*12} {'─'*10} {'─'*9} {'─'*10} {'─'*10} {'─'*8}{'  ' + '─'*10 if show_dollars else ''}")

    for _, row in daily.iterrows():
        rec = f"{int(row['W'])}W-{int(row['L'])}L"
        trend_icon = '📈' if row['Units'] > 0 else '📉' if row['Units'] < 0 else '➡️'
        dollar_str = f"  ${row['DollarPL']:>+9,.2f}" if show_dollars else ''
        print(f"  {row['Date']:<12} {rec:<10} {row['Units']:+.1f}{'':<4} {row['CumUnits']:+.1f}{'':<5} {row['RollingRate']:.1%}{'':<5} {trend_icon}{dollar_str}")

    # ASCII Profit Curve
    section("Cumulative Profit Curve (units)")
    values = daily['CumUnits'].tolist()
    dates_list = daily['Date'].tolist()
    if values:
        max_val = max(abs(v) for v in values) or 1
        chart_height = 10
        for level in range(chart_height, -chart_height - 1, -1):
            threshold = (level / chart_height) * max_val
            line = f"  {threshold:>+6.1f} │"
            for v in values:
                if level == 0:
                    line += '─'
                elif level > 0 and v >= threshold:
                    line += '█'
                elif level < 0 and v <= threshold:
                    line += '█'
                else:
                    line += ' '
            print(line)
        print(f"  {'':>6} └{'─' * len(values)}")
        # Date labels
        label_line = f"  {'':>7}"
        for i, d in enumerate(dates_list):
            if i == 0 or i == len(dates_list) - 1:
                label_line = label_line[:7 + i] + d[-5:]
                label_line += ' ' * max(0, 7 + len(dates_list) - len(label_line))
        print(label_line.rstrip())


# ═══════════════════════════════════════════════════════════════════════════════
#  5. BANKROLL TRACKER
# ═══════════════════════════════════════════════════════════════════════════════

BANKROLL_FILE = "bankroll.json"


def load_bankroll():
    """Load bankroll settings from bankroll.json."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), BANKROLL_FILE)
    if os.path.exists(path):
        import json
        with open(path) as f:
            return json.load(f)
    return None


def save_bankroll(data):
    """Save bankroll settings to bankroll.json."""
    import json
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), BANKROLL_FILE)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def bankroll_tracker():
    """Track bankroll over time using flat units or real dollars."""
    header("💵 BANKROLL TRACKER")

    bankroll_data = load_bankroll()
    if bankroll_data is None:
        section("Setup — First Time")
        print("  No bankroll configured yet. Let's set one up.\n")
        try:
            starting = float(input("  Starting bankroll ($): ").strip().replace('$', '').replace(',', ''))
        except (ValueError, EOFError):
            print("  ❌ Invalid amount.")
            return
        try:
            unit_str = input("  Unit size ($ per flat bet, default = bankroll/100): ").strip().replace('$', '').replace(',', '')
            unit_size = float(unit_str) if unit_str else round(starting / 100, 2)
        except (ValueError, EOFError):
            unit_size = round(starting / 100, 2)

        bankroll_data = {
            "starting_bankroll": starting,
            "unit_size": unit_size,
            "created": datetime.now().strftime('%Y-%m-%d')
        }
        save_bankroll(bankroll_data)
        print(f"\n  ✅ Bankroll saved: ${starting:,.2f} | Unit size: ${unit_size:,.2f}")

    starting = bankroll_data['starting_bankroll']
    unit_size = bankroll_data['unit_size']

    # Load all completed bets
    df = load_all_trackers()
    completed = filter_completed(df)

    if completed.empty:
        section("Summary")
        print(f"  Starting Bankroll:  ${starting:,.2f}")
        print(f"  Unit Size:          ${unit_size:,.2f}")
        print("  No completed bets yet.")
        return

    dates = sorted(completed['Date'].unique())
    has_dollars = has_bet_data(completed)

    section("Configuration")
    print(f"  Starting Bankroll:  ${starting:,.2f}")
    print(f"  Unit Size:          ${unit_size:,.2f}")
    print(f"  Tracking Since:     {bankroll_data.get('created', dates[0])}")

    # Day-by-day bankroll
    section("Daily Bankroll")
    print(f"  {'Date':<12} {'Record':<10} {'Day P/L':<12} {'Balance':<12} {'vs Start'}")
    print(f"  {'─'*12} {'─'*10} {'─'*12} {'─'*12} {'─'*10}")

    balance = starting
    for d in dates:
        day_df = completed[completed['Date'] == d]
        w = (day_df['Result'] == 'WIN').sum()
        l = (day_df['Result'] == 'LOSS').sum()
        rec = f"{w}W-{l}L"

        # Use real dollars if available, otherwise unit_size * flat units
        if has_dollars:
            day_df_copy = day_df.copy()
            day_df_copy['RealPL'] = day_df_copy.apply(calc_real_dollars, axis=1)
            tracked = day_df_copy.dropna(subset=['RealPL'])
            if not tracked.empty:
                day_pl = tracked['RealPL'].sum()
            else:
                day_pl = day_df.apply(calc_units, axis=1).sum() * unit_size
        else:
            day_pl = day_df.apply(calc_units, axis=1).sum() * unit_size

        balance += day_pl
        change = balance - starting
        change_pct = (change / starting) * 100 if starting != 0 else 0.0
        icon = '📈' if day_pl >= 0 else '📉'
        print(f"  {d:<12} {rec:<10} {icon} ${day_pl:>+9,.2f}  ${balance:>10,.2f}  {change_pct:+.1f}%")

    section("💰 Bankroll Summary")
    total_change = balance - starting
    total_pct = (total_change / starting) * 100 if starting != 0 else 0.0
    print(f"  Starting:     ${starting:,.2f}")
    print(f"  Current:      ${balance:,.2f}")
    print(f"  Net Change:   ${total_change:+,.2f}  ({total_pct:+.1f}%)")

    if balance <= 0:
        print("\n  🔴 BUSTED — bankroll depleted.")
    elif balance < starting * 0.8:
        print(f"\n  ⚠️  Down {abs(total_pct):.0f}% — consider reducing unit size.")
    elif balance > starting * 1.2:
        print(f"\n  🔥 Up {total_pct:.0f}% — consider increasing unit size to ${balance / 100:,.2f}.")
    else:
        print(f"\n  📊 Bankroll within normal range.")

    # Kelly recommendation
    total_bets = len(completed)
    wins = (completed['Result'] == 'WIN').sum()
    if total_bets >= 10:
        wr = wins / total_bets
        section("Kelly Bet Sizing Recommendation")
        # Quarter-kelly at -110
        edge = wr - (1 - wr) * 1.1
        full_kelly = max(0, edge / 1.0)  # fraction of bankroll
        quarter_kelly = full_kelly / 4
        recommended_bet = balance * quarter_kelly
        print(f"  Lifetime Win Rate:  {wr:.1%}")
        print(f"  Full Kelly:         {full_kelly:.1%} of bankroll")
        print(f"  Quarter-Kelly:      {quarter_kelly:.1%} of bankroll")
        print(f"  Recommended Bet:    ${recommended_bet:,.2f} per play")
        if recommended_bet <= 0:
            print("  ⚠️  Kelly says don't bet — no edge detected yet.")


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN MENU
# ═══════════════════════════════════════════════════════════════════════════════

def list_available_dates():
    """Show available bet tracker dates."""
    pattern = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bet_tracker_*.csv')
    files = sorted(glob.glob(pattern))
    dates = []
    for f in files:
        match = re.search(r'bet_tracker_(\d{4}-\d{2}-\d{2})\.csv', f)
        if match:
            dates.append(match.group(1))
    return dates


def main():
    print("\n" + "=" * 65)
    print("  🏀 NBA Prediction Engine — Post-Mortem Analyzer")
    print("=" * 65)

    while True:
        print("\n  [1] Single-Day Post-Mortem")
        print("  [2] Lifetime Performance Dashboard")
        print("  [3] Edge Calibration Report")
        print("  [4] Daily Trend & Profit Curve")
        print("  [5] Bankroll Tracker")
        print("  [Q] Quit\n")

        choice = input("  Select: ").strip().upper()

        if choice == 'Q':
            print("  👋 Done.")
            break

        elif choice == '1':
            dates = list_available_dates()
            if dates:
                print(f"\n  Available dates: {', '.join(dates)}")
            date_str = input("  Enter date (YYYY-MM-DD): ").strip()
            daily_post_mortem(date_str)

        elif choice == '2':
            lifetime_dashboard()

        elif choice == '3':
            edge_calibration_report()

        elif choice == '4':
            daily_trend()

        elif choice == '5':
            bankroll_tracker()

        else:
            print("  ❌ Invalid choice.")


if __name__ == "__main__":
    main()
