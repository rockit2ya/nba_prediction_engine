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
import json
from datetime import datetime

# ─── Constants ────────────────────────────────────────────────────────────────
BREAKEVEN_RATE = 0.524          # ATS break-even at -110 odds
VIG = -110                      # Standard juice
HIGH_SIGNAL_EDGE = 5            # Minimum edge for "high-signal" bets
DEFAULT_EDGE_CAP = 10

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


def load_edge_cap():
    """Load edge cap from bankroll.json, falling back to default."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bankroll.json')
    try:
        with open(path) as f:
            return json.load(f).get('edge_cap', DEFAULT_EDGE_CAP)
    except (FileNotFoundError, json.JSONDecodeError):
        return DEFAULT_EDGE_CAP


def get_raw_edge(row):
    """Get the uncapped edge for a bet row.

    Priority: Raw_Edge column > reconstruct from abs(Fair - Market) > fallback to Edge.
    """
    # 1. Use Raw_Edge column if present and valid
    if 'Raw_Edge' in row.index:
        try:
            val = float(row['Raw_Edge'])
            if val > 0:
                return val
        except (ValueError, TypeError):
            pass
    # 2. Reconstruct from Fair and Market columns
    try:
        fair = float(row['Fair'])
        market = float(row['Market'])
        return round(abs(fair - market), 2)
    except (ValueError, TypeError, KeyError):
        pass
    # 3. Fallback: use the (possibly capped) Edge column
    try:
        return float(row['Edge'])
    except (ValueError, TypeError):
        return 0.0


def is_edge_capped(row, edge_cap=None):
    """Determine if a bet's edge was capped.

    Priority: Edge_Capped column > compare raw_edge to cap.
    """
    # 1. Use Edge_Capped column if present
    if 'Edge_Capped' in row.index:
        val = str(row['Edge_Capped']).strip().upper()
        if val in ('YES', 'TRUE', '1'):
            return True
        if val in ('NO', 'FALSE', '0'):
            return False
    # 2. Infer from raw edge vs cap
    if edge_cap is None:
        edge_cap = load_edge_cap()
    return get_raw_edge(row) > edge_cap


def build_edge_tiers(edge_cap=None):
    """Build dynamic edge tiers based on the current edge cap."""
    if edge_cap is None:
        edge_cap = load_edge_cap()
    half = edge_cap / 2
    tiers = [(half, edge_cap), (edge_cap, edge_cap * 1.5), (edge_cap * 1.5, float('inf'))]
    labels = [f'{half:.0f}–{edge_cap:.0f}', f'{edge_cap:.0f}–{edge_cap * 1.5:.0f}', f'{edge_cap * 1.5:.0f}+']
    return tiers, labels


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
    all_pushes = completed[completed['Result'] == 'PUSH']
    pending = df[df['Result'] == 'PENDING']

    header(f"📅 Daily Post-Mortem: {date_str}")

    # Overall day stats
    print(f"\n  Total bets logged:    {len(df)}")
    print(f"  Completed:            {len(completed)}  (Pending: {len(pending)})")
    print(f"  Wins: {len(all_wins)} | Losses: {len(all_losses)} | Pushes: {len(all_pushes)}")

    if len(completed) > 0:
        decided = len(all_wins) + len(all_losses)  # exclude PUSHes from win-rate
        day_rate = len(all_wins) / decided if decided > 0 else 0
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
            print(f"  Win Rate: {len(hw)/(len(hw)+len(hl)):.1%}" if (len(hw)+len(hl)) > 0 else "  Win Rate: N/A")

    # Loss analysis
    injuries = load_injuries()
    if not all_losses.empty:
        section("Loss Analysis")
        edge_cap = load_edge_cap()
        loss_margins = []
        injury_count = 0
        low_edge_count = 0
        capped_count = 0

        for _, row in all_losses.iterrows():
            margin = parse_margin(row)
            notes = str(row.get('Notes', ''))
            raw = get_raw_edge(row)
            capped = is_edge_capped(row, edge_cap)
            cap_tag = f" ⚠️ CAPPED (raw: {raw})" if capped else ""
            print(f"  ❌ {row['Away']} @ {row['Home']} | Pick: {row['Pick']} | Edge: {row['Edge']}{cap_tag}")
            if margin is not None:
                print(f"     Margin: {margin}  |  {notes}")
                loss_margins.append(margin)
            if capped:
                capped_count += 1

            # Injury check (alias-aware matching — Pick is nickname, CSV has full name)
            if injuries is not None:
                team_inj = injuries[injuries['team'].apply(lambda t: names_match(t, str(row['Pick'])))]
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
        if capped_count:
            print(f"  Losses with edge capped:    {capped_count}")
        if loss_margins:
            print(f"  Avg margin of defeat:       {sum(loss_margins)/len(loss_margins):.1f}")

    # Win analysis
    if not all_wins.empty:
        section("Win Analysis")
        edge_cap = load_edge_cap()
        win_margins = []
        for _, row in all_wins.iterrows():
            margin = parse_margin(row)
            notes = str(row.get('Notes', ''))
            raw = get_raw_edge(row)
            capped = is_edge_capped(row, edge_cap)
            cap_tag = f" ⚠️ CAPPED (raw: {raw})" if capped else ""
            print(f"  ✅ {row['Away']} @ {row['Home']} | Pick: {row['Pick']} | Edge: {row['Edge']}{cap_tag}")
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
    pushes = completed[completed['Result'] == 'PUSH']
    pending = df[df['Result'] == 'PENDING']
    dates = sorted(completed['Date'].unique())

    header("🏆 LIFETIME PERFORMANCE DASHBOARD")

    # ── Overview ──
    section("Overview")
    total = len(completed)
    decided = len(wins) + len(losses)  # exclude PUSHes from win-rate
    win_rate = len(wins) / decided if decided > 0 else 0
    total_units = completed.apply(calc_units, axis=1).sum()
    roi = (total_units / (decided * 1.1)) * 100 if decided > 0 else 0  # ROI = profit / total risked

    print(f"  Date Range:      {dates[0]} → {dates[-1]}  ({len(dates)} day(s))")
    print(f"  Total Bets:      {len(df)}  (Completed: {total}, Pending: {len(pending)})")
    print(f"  Record:          {len(wins)}W - {len(losses)}L - {len(pushes)}P")
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
                else:
                    print(f"\n  💡 Tip: Enter a sportsbook name when logging bets for per-book P/L breakdown.")
        else:
            section("💰 Real Money P/L")
            print("  ⚠️  No dollar amounts tracked yet.")
            print("     Enter Odds and Bet amount when logging bets to enable real money tracking.")
    else:
        section("💰 Real Money P/L")
        print("  ⚠️  No dollar amounts tracked yet.")
        print("     Enter Odds and Bet amount when logging bets to enable real money tracking.")

    # ── Confidence Breakdown ──
    if 'Confidence' in completed.columns:
        conf_col = completed['Confidence'].astype(str).str.strip().str.upper()
        conf_vals = conf_col[~conf_col.isin(['', 'NAN'])]
        if not conf_vals.empty:
            section("Confidence Breakdown")
            print(f"  {'Grade':<28} {'Bets':<6} {'Record':<10} {'Win Rate':<10} {'P/L'}")
            print(f"  {'─'*28} {'─'*6} {'─'*10} {'─'*10} {'─'*10}")
            for conf_label in ['HIGH', 'MEDIUM', 'LOW']:
                mask = conf_col.str.contains(conf_label, na=False)
                grp = completed[mask]
                if grp.empty:
                    continue
                cw = (grp['Result'] == 'WIN').sum()
                cl = (grp['Result'] == 'LOSS').sum()
                cd = cw + cl
                cr = cw / cd if cd > 0 else 0
                cu = grp.apply(calc_units, axis=1).sum()
                print(f"  {conf_label:<28} {len(grp):<6} {cw}W-{cl}L{'':<4} {cr:.1%}{'':<5} {cu:+.1f}")
        else:
            section("Confidence Breakdown")
            print("  ⚠️  No confidence data. Star Tax API may have timed out during analysis.")
    else:
        section("Confidence Breakdown")
        print("  ⚠️  No confidence data. Older bet trackers may not include this column.")

    # ── Bet Type Breakdown ──
    if 'Type' in completed.columns:
        type_col = completed['Type'].astype(str).str.strip()
        type_vals = type_col[~type_col.isin(['', 'nan'])]
        if not type_vals.empty and type_vals.nunique() > 1:
            section("Bet Type Breakdown")
            print(f"  {'Type':<16} {'Bets':<6} {'Record':<10} {'Win Rate':<10} {'P/L'}")
            print(f"  {'─'*16} {'─'*6} {'─'*10} {'─'*10} {'─'*10}")
            for bt in sorted(type_vals.unique()):
                grp = completed[type_col == bt]
                tw_ = (grp['Result'] == 'WIN').sum()
                tl_ = (grp['Result'] == 'LOSS').sum()
                td_ = tw_ + tl_
                tr_ = tw_ / td_ if td_ > 0 else 0
                tu_ = grp.apply(calc_units, axis=1).sum()
                print(f"  {bt:<16} {len(grp):<6} {tw_}W-{tl_}L{'':<4} {tr_:.1%}{'':<5} {tu_:+.1f}")

    # ── High-Signal Only ──
    high = filter_high_signal(completed)
    if not high.empty:
        hw = high[high['Result'] == 'WIN']
        hl = high[high['Result'] == 'LOSS']
        high_decided = len(hw) + len(hl)
        high_rate = len(hw) / high_decided if high_decided > 0 else 0
        high_units = high.apply(calc_units, axis=1).sum()
        high_roi = (high_units / (high_decided * 1.1)) * 100 if high_decided > 0 else 0

        high_kelly = high.apply(calc_kelly_units, axis=1).sum()
        section("High-Signal Bets (Edge ≥ 5)")
        print(f"  A 'high-signal' bet is any pick where the model's edge is {HIGH_SIGNAL_EDGE}+ pts.")
        print(f"  These are your highest-conviction plays and should win at a higher rate.\n")
        print(f"  Record:          {len(hw)}W - {len(hl)}L")
        print(f"  Win Rate:        {high_rate:.1%}")
        print(f"  Grade:           {grade_win_rate(high_rate, len(high))}")
        print(f"  P/L:             {high_units:+.1f} units  (Kelly-sized: {high_kelly:+.2f} units)")
        print(f"  ROI:             {high_roi:+.1f}%")

    # ── CLV (Closing Line Value) ──
    if 'CLV' in completed.columns:
        clv_col = pd.to_numeric(completed['CLV'], errors='coerce')
        clv_valid = completed[clv_col.notna()].copy()
        clv_valid['CLV_num'] = pd.to_numeric(clv_valid['CLV'], errors='coerce')
        if not clv_valid.empty:
            section("📈 Closing Line Value (CLV)")
            avg_clv = clv_valid['CLV_num'].mean()
            pos_clv = (clv_valid['CLV_num'] > 0).sum()
            neg_clv = (clv_valid['CLV_num'] < 0).sum()
            zero_clv = (clv_valid['CLV_num'] == 0).sum()
            clv_rate = pos_clv / len(clv_valid) if len(clv_valid) > 0 else 0

            # CLV by result
            clv_wins = clv_valid[clv_valid['Result'] == 'WIN']['CLV_num']
            clv_losses = clv_valid[clv_valid['Result'] == 'LOSS']['CLV_num']

            print(f"  Tracked Bets:    {len(clv_valid)} of {len(completed)} completed")
            print(f"  Average CLV:     {avg_clv:+.2f} pts")
            print(f"  Positive CLV:    {pos_clv} ({clv_rate:.0%}) — you beat the closing line")
            print(f"  Negative CLV:    {neg_clv}")
            if not clv_wins.empty:
                print(f"  CLV on Wins:     {clv_wins.mean():+.2f} avg")
            if not clv_losses.empty:
                print(f"  CLV on Losses:   {clv_losses.mean():+.2f} avg")

            if avg_clv > 0:
                print(f"\n  ✅ Positive average CLV — model is finding real value before the market adjusts.")
            elif avg_clv > -0.5:
                print(f"\n  ⚠️  CLV near zero — model tracks the market but isn't consistently beating it.")
            else:
                print(f"\n  🔴 Negative CLV — consider betting earlier or reviewing what moves lines after you bet.")
        else:
            section("📈 Closing Line Value (CLV)")
            print("  ⚠️  No CLV data yet. To enable CLV tracking:")
            print("     1. Run: bash fetch_all_nba_data.sh (close to tip-off for best results)")
            print("     2. Run: python update_results.py (after games finish)")
            print("     CLV columns will auto-populate in your bet tracker CSVs.")
    else:
        section("📈 Closing Line Value (CLV)")
        print("  ⚠️  No CLV data yet. To enable CLV tracking:")
        print("     1. Run: bash fetch_all_nba_data.sh (close to tip-off for best results)")
        print("     2. Run: python update_results.py (after games finish)")
        print("     CLV columns will auto-populate in your bet tracker CSVs.")

    # ── Edge Cap Audit ──
    edge_cap = load_edge_cap()
    completed_audit = completed.copy()
    completed_audit['Raw_Edge_Val'] = completed_audit.apply(get_raw_edge, axis=1)
    completed_audit['Was_Capped'] = completed_audit.apply(lambda r: is_edge_capped(r, edge_cap), axis=1)
    capped_bets = completed_audit[completed_audit['Was_Capped']]
    uncapped_bets = completed_audit[~completed_audit['Was_Capped']]

    section(f"🔒 Edge Cap Audit (cap = {edge_cap} pts)")
    n_capped = len(capped_bets)
    n_total = len(completed_audit)
    print(f"  Current Edge Cap:     {edge_cap} pts")
    print(f"  Capped Bets:          {n_capped} of {n_total} ({n_capped/n_total:.0%})" if n_total > 0 else "  Capped Bets:  0")

    if n_capped > 0:
        # Capped vs. uncapped win rates
        capped_w = (capped_bets['Result'] == 'WIN').sum()
        capped_l = (capped_bets['Result'] == 'LOSS').sum()
        capped_decided = capped_w + capped_l
        capped_rate = capped_w / capped_decided if capped_decided > 0 else 0
        capped_units = capped_bets.apply(calc_units, axis=1).sum()

        uncapped_w = (uncapped_bets['Result'] == 'WIN').sum()
        uncapped_l = (uncapped_bets['Result'] == 'LOSS').sum()
        uncapped_decided = uncapped_w + uncapped_l
        uncapped_rate = uncapped_w / uncapped_decided if uncapped_decided > 0 else 0
        uncapped_units = uncapped_bets.apply(calc_units, axis=1).sum()

        print(f"\n  {'Category':<20} {'Record':<12} {'Win Rate':<12} {'P/L'}")
        print(f"  {'─'*20} {'─'*12} {'─'*12} {'─'*10}")
        print(f"  {'Capped (>' + str(int(edge_cap)) + ')':<20} {f'{capped_w}W-{capped_l}L':<12} {capped_rate:.1%}{'':<7} {capped_units:+.1f}")
        print(f"  {'Uncapped (≤' + str(int(edge_cap)) + ')':<20} {f'{uncapped_w}W-{uncapped_l}L':<12} {uncapped_rate:.1%}{'':<7} {uncapped_units:+.1f}")

        # Raw edge distribution for capped bets
        raw_edges = capped_bets['Raw_Edge_Val']
        print(f"\n  Capped Edge Distribution:")
        print(f"    Min raw edge:    {raw_edges.min():.1f} pts")
        print(f"    Max raw edge:    {raw_edges.max():.1f} pts")
        print(f"    Avg raw edge:    {raw_edges.mean():.1f} pts")
        print(f"    Median raw edge: {raw_edges.median():.1f} pts")

        # Individual capped bets
        print(f"\n  Capped Bet Log:")
        for _, row in capped_bets.iterrows():
            result_icon = '✅' if row['Result'] == 'WIN' else '❌' if row['Result'] == 'LOSS' else '➡️'
            print(f"    {result_icon} {row['Away']} @ {row['Home']} | Raw: {row['Raw_Edge_Val']:.1f} → Capped: {row['Edge']} | {row['Result']}")

        # Recommendation
        print()
        if capped_decided >= 5:
            if capped_rate < uncapped_rate and capped_rate < BREAKEVEN_RATE:
                print(f"  🔴 Capped bets winning at {capped_rate:.0%} vs {uncapped_rate:.0%} uncapped.")
                print(f"     → The cap is doing its job. Consider lowering it further.")
            elif capped_rate >= uncapped_rate and capped_rate >= BREAKEVEN_RATE:
                print(f"  📈 Capped bets winning at {capped_rate:.0%} vs {uncapped_rate:.0%} uncapped.")
                print(f"     → Capped bets are profitable — consider raising the cap to capture more edge.")
            else:
                print(f"  ⚠️  Mixed signals. Keep the cap at {int(edge_cap)} and revisit after more data.")
        else:
            print(f"  ⚠️  Only {capped_decided} decided capped bets — need 5+ for meaningful recommendation.")
    else:
        print("  ✅ No edges have exceeded the cap yet.")
    print(f"\n  💡 Adjust the cap: post_mortem.py → [5] Bankroll Tracker → [R] Reset Settings → Edge Cap")

    # ── Edge Calibration (uses raw edges) ──
    EDGE_TIERS, EDGE_TIER_LABELS = build_edge_tiers(edge_cap)
    section("Edge Calibration (do bigger edges win more?)")
    print(f"  {'Tier':<10} {'Record':<12} {'Win Rate':<12} {'P/L':<10} {'Verdict'}")
    print(f"  {'─'*10} {'─'*12} {'─'*12} {'─'*10} {'─'*15}")

    calibration_ok = True
    prev_rate = None  # None means no previous tier with data yet
    tier_rates = []   # collect (label, rate, n) for all non-empty tiers
    completed_cal = completed.copy()
    completed_cal['_RawEdge'] = completed_cal.apply(get_raw_edge, axis=1)
    for (lo, hi_bound), label in zip(EDGE_TIERS, EDGE_TIER_LABELS):
        tier = completed_cal[(completed_cal['_RawEdge'] >= lo) & (completed_cal['_RawEdge'] < hi_bound)]
        if tier.empty:
            print(f"  {label:<10} {'—':<12} {'—':<12} {'—':<10} No data")
            continue
        tw = tier[tier['Result'] == 'WIN']
        tl = tier[tier['Result'] == 'LOSS']
        tier_decided = len(tw) + len(tl)
        tr = len(tw) / tier_decided if tier_decided > 0 else 0
        tu = tier.apply(calc_units, axis=1).sum()
        tier_rates.append((label, tr, len(tier)))

        verdict = "✅" if tr >= BREAKEVEN_RATE else "⚠️"
        # Check inversion: if this tier's rate is lower than ANY previous tier
        if prev_rate is not None and tr < prev_rate:
            verdict = "🔻 Inverted"
            calibration_ok = False

        print(f"  {label:<10} {f'{len(tw)}W-{len(tl)}L':<12} {tr:.1%}{'':<7} {tu:+.1f}{'':<5} {verdict}")
        prev_rate = tr  # track last non-empty tier rate

    print(f"\n  Note: Tiers use raw (uncapped) edges. Tiers adjust with your cap ({int(edge_cap)} pts).")

    if calibration_ok and len(tier_rates) >= 2:
        print("  ✅ Calibration: Higher edges are winning at higher rates — model is well-calibrated.")
    elif calibration_ok:
        print("  ⚠️  Calibration: Not enough tier data to fully assess (need 2+ tiers with bets).")
    else:
        print("  ⚠️  Calibration issue: A lower-edge tier is outperforming a higher one.")
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

    # Max win/loss streaks (PUSHes don't break streaks)
    max_w_streak = max_l_streak = cur_w = cur_l = 0
    for r in result_labels:
        if r == 'WIN':
            cur_w += 1
            cur_l = 0
        elif r == 'LOSS':
            cur_l += 1
            cur_w = 0
        # PUSH: don't reset either streak
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
    daily['Decided'] = daily['W'] + daily['L']
    daily['WinRate'] = daily.apply(lambda r: r['W'] / r['Decided'] if r['Decided'] > 0 else 0, axis=1)
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

    # Check 3: High-signal win rate (bets with edge >= 5 pts)
    if not high.empty:
        high_wr = len(hw) / (len(hw) + len(hl)) if (len(hw) + len(hl)) > 0 else 0
        checks.append((f"High-Signal (Edge ≥ {HIGH_SIGNAL_EDGE}) Win Rate > 55%", high_wr >= 0.55, f"{high_wr:.1%}"))

    # Check 4: Edge calibration
    checks.append(("Edge Calibration (higher edges win more)", calibration_ok, ""))

    # Check 5: Sample size
    checks.append(("Sufficient Sample (20+ bets)", total >= 20, f"n={total}"))

    # Check 6: CLV (if data available)
    if 'CLV' in completed.columns:
        clv_col_v = pd.to_numeric(completed['CLV'], errors='coerce')
        clv_valid_v = clv_col_v.dropna()
        if len(clv_valid_v) >= 5:
            avg_clv_v = clv_valid_v.mean()
            checks.append(("Positive CLV (beating closing lines)", avg_clv_v > 0, f"{avg_clv_v:+.2f} pts"))

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
    elif win_rate >= BREAKEVEN_RATE and roi > 0:
        print("  📈 VERDICT: Model is profitable — keep building sample size.")
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
    print("  Note: Uses raw (uncapped) edges for accurate bucketing.\n")

    # Compute raw edges for each bet
    completed = completed.copy()
    completed['_RawEdge'] = completed.apply(get_raw_edge, axis=1)

    # Fine-grained edge buckets
    buckets = [(0, 3), (3, 5), (5, 8), (8, 10), (10, 15), (15, 20), (20, float('inf'))]
    bucket_labels = ['0–3', '3–5', '5–8', '8–10', '10–15', '15–20', '20+']

    print(f"  {'Edge':<10} {'Bets':<8} {'Record':<12} {'Win Rate':<12} {'P/L':<10} {'Avg Margin'}")
    print(f"  {'─'*10} {'─'*8} {'─'*12} {'─'*12} {'─'*10} {'─'*12}")

    for (lo, hi_bound), label in zip(buckets, bucket_labels):
        tier = completed[(completed['_RawEdge'] >= lo) & (completed['_RawEdge'] < hi_bound)]
        if tier.empty:
            print(f"  {label:<10} {'0':<8} {'—':<12} {'—':<12} {'—':<10} {'—'}")
            continue

        tw = tier[tier['Result'] == 'WIN']
        tl = tier[tier['Result'] == 'LOSS']
        tier_decided = len(tw) + len(tl)
        tr = len(tw) / tier_decided if tier_decided > 0 else 0
        tu = tier.apply(calc_units, axis=1).sum()

        margins = [m for m in (parse_margin(row) for _, row in tier.iterrows()) if m is not None]
        avg_m = f"{sum(margins)/len(margins):+.1f}" if margins else "—"

        bar = '█' * int(tr * 20) + '░' * (20 - int(tr * 20))
        print(f"  {label:<10} {len(tier):<8} {f'{len(tw)}W-{len(tl)}L':<12} {tr:.1%} {bar} {tu:+.1f}{'':<5} {avg_m}")

    # Correlation check (uses raw edges)
    section("Edge vs. Win Rate Correlation")
    completed_with_margin = completed.copy()
    completed_with_margin['won'] = (completed_with_margin['Result'] == 'WIN').astype(int)
    try:
        corr = completed_with_margin[['_RawEdge', 'won']].corr().loc['_RawEdge', 'won']
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
    daily['CumDecided'] = (daily['W'] + daily['L']).cumsum()
    daily['RollingRate'] = daily.apply(lambda r: r['CumW'] / r['CumDecided'] if r['CumDecided'] > 0 else 0, axis=1)

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

        try:
            cap_str = input("  Edge cap (max edge before warning, default = 10): ").strip().lower().replace('pts', '').replace('pt', '').strip()
            edge_cap = int(cap_str) if cap_str else 10
        except (ValueError, EOFError):
            edge_cap = 10

        bankroll_data = {
            "starting_bankroll": starting,
            "unit_size": unit_size,
            "edge_cap": edge_cap,
            "created": datetime.now().strftime('%Y-%m-%d')
        }
        save_bankroll(bankroll_data)
        print(f"\n  ✅ Bankroll saved: ${starting:,.2f} | Unit size: ${unit_size:,.2f} | Edge cap: {edge_cap} pts")

    starting = bankroll_data['starting_bankroll']
    unit_size = bankroll_data['unit_size']
    edge_cap = bankroll_data.get('edge_cap', 10)

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
    print(f"  Edge Cap:           {edge_cap} pts")
    print(f"  Tracking Since:     {bankroll_data.get('created', dates[0])}")
    print(f"\n  [R] Reset Settings   [Enter] Continue\n")

    choice = input("  ").strip().upper()
    if choice == 'R':
        print()
        try:
            new_start = float(input(f"  New starting bankroll (current: ${starting:,.2f}): $").strip().replace('$', '').replace(',', ''))
        except (ValueError, EOFError):
            print("  ❌ Invalid amount. Keeping current settings.")
            return
        try:
            new_unit_str = input(f"  New unit size (current: ${unit_size:,.2f}, default = bankroll/100): $").strip().replace('$', '').replace(',', '')
            new_unit = float(new_unit_str) if new_unit_str else round(new_start / 100, 2)
        except (ValueError, EOFError):
            new_unit = round(new_start / 100, 2)
        try:
            cap_str = input(f"  New edge cap (current: {edge_cap} pts, Enter to keep): ").strip().lower().replace('pts', '').replace('pt', '').strip()
            new_cap = int(cap_str) if cap_str else edge_cap
        except (ValueError, EOFError):
            new_cap = edge_cap

        bankroll_data = {
            "starting_bankroll": new_start,
            "unit_size": new_unit,
            "edge_cap": new_cap,
            "created": datetime.now().strftime('%Y-%m-%d')
        }
        save_bankroll(bankroll_data)
        starting = new_start
        unit_size = new_unit
        edge_cap = new_cap
        print(f"\n  ✅ Settings updated: ${starting:,.2f} | Unit: ${unit_size:,.2f} | Edge cap: {edge_cap} pts\n")

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
    losses = (completed['Result'] == 'LOSS').sum()
    decided = wins + losses
    if decided >= 10:
        wr = wins / decided
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
