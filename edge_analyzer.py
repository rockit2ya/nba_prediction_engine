#!/usr/bin/env python3
"""
edge_analyzer.py — NBA Prediction Engine Edge Decomposition & Diagnostics

Breaks down every factor in the fair line calculation so you can see
exactly what is driving each prediction and catch model issues early.

Features:
  [1] Live Matchup Decomposition — full factor breakdown for any matchup
  [2] Historical Edge Audit — replay past bets with factor breakdowns
  [3] Factor Contribution Report — which factors matter most across all bets
  [4] Model Health Check — automated diagnostics for calibration issues

Usage:
    python edge_analyzer.py
"""

import pandas as pd
import glob
import os
import re
import json
import difflib
from datetime import datetime
from nba_analytics import (
    calculate_pace_and_ratings,
    get_injuries,
    get_news,
    get_star_tax_weighted,
    get_rest_penalty,
    LEAGUE_BASELINE,
    CACHE_FILE,
)

# ─── Constants ────────────────────────────────────────────────────────────────
REGRESS_FACTOR = 0.75
HCA_FLAT = 3.0
EDGE_TIERS = [(0, 3), (3, 5), (5, 8), (8, 10), (10, 15), (15, 20), (20, float('inf'))]
EDGE_TIER_LABELS = ['0–3', '3–5', '5–8', '8–10', '10–15', '15–20', '20+']

SHORT_TO_FULL = {
    'Hawks': 'Atlanta Hawks', 'Celtics': 'Boston Celtics', 'Nets': 'Brooklyn Nets',
    'Hornets': 'Charlotte Hornets', 'Bulls': 'Chicago Bulls', 'Cavaliers': 'Cleveland Cavaliers',
    'Mavericks': 'Dallas Mavericks', 'Nuggets': 'Denver Nuggets', 'Pistons': 'Detroit Pistons',
    'Warriors': 'Golden State Warriors', 'Rockets': 'Houston Rockets', 'Pacers': 'Indiana Pacers',
    'Clippers': 'LA Clippers', 'Lakers': 'Los Angeles Lakers', 'Grizzlies': 'Memphis Grizzlies',
    'Heat': 'Miami Heat', 'Bucks': 'Milwaukee Bucks', 'Timberwolves': 'Minnesota Timberwolves',
    'Pelicans': 'New Orleans Pelicans', 'Knicks': 'New York Knicks', 'Thunder': 'Oklahoma City Thunder',
    'Magic': 'Orlando Magic', '76ers': 'Philadelphia 76ers', 'Suns': 'Phoenix Suns',
    'Trail Blazers': 'Portland Trail Blazers', 'Kings': 'Sacramento Kings', 'Spurs': 'San Antonio Spurs',
    'Raptors': 'Toronto Raptors', 'Jazz': 'Utah Jazz', 'Wizards': 'Washington Wizards',
}


# ═══════════════════════════════════════════════════════════════════════════════
#  CORE: Factor Decomposition Engine
# ═══════════════════════════════════════════════════════════════════════════════

def fuzzy_team_match(name, team_list):
    if name in team_list:
        return name
    if name in SHORT_TO_FULL and SHORT_TO_FULL[name] in team_list:
        return SHORT_TO_FULL[name]
    matches = difflib.get_close_matches(name, team_list, n=1, cutoff=0.7)
    return matches[0] if matches else name


def decompose_edge(away_team, home_team, market_line=None):
    """
    Full factor decomposition for a matchup.
    Returns a dict with every component that goes into the fair line.
    """
    ratings = calculate_pace_and_ratings()
    team_names = ratings['TEAM_NAME'].tolist()
    h_team = fuzzy_team_match(home_team, team_names)
    a_team = fuzzy_team_match(away_team, team_names)

    try:
        h_row = ratings[ratings['TEAM_NAME'] == h_team].iloc[0]
        a_row = ratings[ratings['TEAM_NAME'] == a_team].iloc[0]
    except IndexError:
        raise Exception(f"Team not found: {away_team} or {home_team}")

    injuries = get_injuries()
    news = get_news()

    # --- Raw ratings (pre-regression) ---
    h_off_raw, h_def_raw = h_row['OFF_RATING'], h_row['DEF_RATING']
    a_off_raw, a_def_raw = a_row['OFF_RATING'], a_row['DEF_RATING']
    h_net_raw = h_row['NET_RATING']
    a_net_raw = a_row['NET_RATING']

    # --- Regressed ratings ---
    h_off = (h_off_raw * REGRESS_FACTOR) + (LEAGUE_BASELINE['OFF_RATING'] * (1 - REGRESS_FACTOR))
    h_def = (h_def_raw * REGRESS_FACTOR) + (LEAGUE_BASELINE['DEF_RATING'] * (1 - REGRESS_FACTOR))
    a_off = (a_off_raw * REGRESS_FACTOR) + (LEAGUE_BASELINE['OFF_RATING'] * (1 - REGRESS_FACTOR))
    a_def = (a_def_raw * REGRESS_FACTOR) + (LEAGUE_BASELINE['DEF_RATING'] * (1 - REGRESS_FACTOR))

    # --- Raw diff (before and after regression) ---
    raw_diff_pre = (h_off_raw - a_def_raw) - (a_off_raw - h_def_raw)
    raw_diff_post = (h_off - a_def) - (a_off - h_def)
    regression_impact = raw_diff_post - raw_diff_pre

    # --- Pace ---
    h_pace, a_pace = h_row['PACE'], a_row['PACE']
    expected_pace = (h_pace + a_pace) / 2
    pace_multiplier = expected_pace / 100

    # --- HCA ---
    hca = HCA_FLAT
    # What the OLD HCA would have been (for comparison)
    old_hca = 3.0 + ((h_net_raw - a_net_raw) / 20)

    # --- Rest ---
    h_rest = get_rest_penalty(h_row['TEAM_ID'])
    a_rest = get_rest_penalty(a_row['TEAM_ID'])
    rest_adj = h_rest - a_rest

    # --- Star Tax ---
    h_injuries = injuries.get(h_row['TEAM_NAME'], [])
    a_injuries = injuries.get(a_row['TEAM_NAME'], [])
    h_tax_raw = get_star_tax_weighted(h_row['TEAM_ID'], h_injuries)
    a_tax_raw = get_star_tax_weighted(a_row['TEAM_ID'], a_injuries)
    star_tax_failed = h_tax_raw is None or a_tax_raw is None
    h_tax = h_tax_raw if h_tax_raw is not None else 0
    a_tax = a_tax_raw if a_tax_raw is not None else 0

    # --- News factor ---
    news_factor = 0
    news_hits = []
    matchup_keywords = set()
    for name in [h_team, a_team, home_team, away_team]:
        matchup_keywords.add(name.lower())
    for name in [h_team, a_team]:
        parts = name.split()
        if parts:
            matchup_keywords.add(parts[-1].lower())
    for item in news:
        combined = item.get('title', '').lower() + ' ' + item.get('summary', '').lower()
        if not any(kw in combined for kw in matchup_keywords):
            continue
        if 'late scratch' in combined:
            news_factor -= 2
            news_hits.append(f"Late scratch: {item.get('title', '')[:60]}")
        if 'coach fired' in combined:
            news_factor -= 1
            news_hits.append(f"Coach fired: {item.get('title', '')[:60]}")

    # --- Assemble fair line ---
    matchup_component = raw_diff_post * pace_multiplier
    fair_line = matchup_component + hca + rest_adj - h_tax + a_tax + news_factor

    # --- What old model would have produced ---
    old_matchup = raw_diff_pre * pace_multiplier
    old_fair_line = old_matchup + old_hca + rest_adj - h_tax + a_tax + news_factor

    # --- Edge ---
    edge = abs(fair_line - market_line) if market_line is not None else None
    old_edge = abs(old_fair_line - market_line) if market_line is not None else None

    return {
        # Teams
        'home': h_team, 'away': a_team,
        # Raw ratings
        'h_off_raw': h_off_raw, 'h_def_raw': h_def_raw, 'h_net_raw': h_net_raw, 'h_pace': h_pace,
        'a_off_raw': a_off_raw, 'a_def_raw': a_def_raw, 'a_net_raw': a_net_raw, 'a_pace': a_pace,
        # Regressed ratings
        'h_off': round(h_off, 2), 'h_def': round(h_def, 2),
        'a_off': round(a_off, 2), 'a_def': round(a_def, 2),
        # Diffs
        'raw_diff_pre': round(raw_diff_pre, 2), 'raw_diff_post': round(raw_diff_post, 2),
        'regression_impact': round(regression_impact, 2),
        # Pace
        'expected_pace': round(expected_pace, 2), 'pace_multiplier': round(pace_multiplier, 4),
        # Components
        'matchup_component': round(matchup_component, 2),
        'hca': hca, 'old_hca': round(old_hca, 2),
        'rest_adj': rest_adj, 'h_rest': h_rest, 'a_rest': a_rest,
        'h_tax': h_tax, 'a_tax': a_tax, 'star_tax_failed': star_tax_failed,
        'news_factor': news_factor, 'news_hits': news_hits,
        'h_injuries': [(p['name'], p['status']) for p in h_injuries],
        'a_injuries': [(p['name'], p['status']) for p in a_injuries],
        # Fair lines
        'fair_line': round(fair_line, 2),
        'old_fair_line': round(old_fair_line, 2),
        'market_line': market_line,
        # Edges
        'edge': round(edge, 2) if edge is not None else None,
        'old_edge': round(old_edge, 2) if old_edge is not None else None,
        # Data quality
        'q_players': [p['name'] for p in (h_injuries + a_injuries) if 'questionable' in p.get('status', '')],
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  DISPLAY: Factor Breakdown
# ═══════════════════════════════════════════════════════════════════════════════

def print_decomposition(d):
    """Pretty-print a full factor decomposition."""
    W = 65
    print("\n" + "=" * W)
    print(f"  🔬 EDGE DECOMPOSITION: {d['away']} @ {d['home']}")
    print("=" * W)

    # Team ratings table
    print("\n  ─── Team Ratings (Raw → Regressed) ───")
    print(f"  {'':20s} {'OFF':>8s} {'DEF':>8s} {'NET':>8s} {'PACE':>8s}")
    print(f"  {'─'*52}")
    print(f"  {d['home'][:20]:20s} {d['h_off_raw']:8.1f} {d['h_def_raw']:8.1f} {d['h_net_raw']:8.1f} {d['h_pace']:8.2f}")
    print(f"  {'  → regressed':20s} {d['h_off']:8.2f} {d['h_def']:8.2f} {'':8s} {'':8s}")
    print(f"  {d['away'][:20]:20s} {d['a_off_raw']:8.1f} {d['a_def_raw']:8.1f} {d['a_net_raw']:8.1f} {d['a_pace']:8.2f}")
    print(f"  {'  → regressed':20s} {d['a_off']:8.2f} {d['a_def']:8.2f} {'':8s} {'':8s}")

    # Factor waterfall
    print(f"\n  ─── Factor Waterfall ───")
    print(f"  {'Factor':<30s} {'Value':>8s} {'Notes'}")
    print(f"  {'─'*60}")
    print(f"  {'Raw Diff (pre-regress)':<30s} {d['raw_diff_pre']:>+8.2f}")
    print(f"  {'Regression adjustment':<30s} {d['regression_impact']:>+8.2f}  (→ {d['raw_diff_post']:+.2f})")
    print(f"  {'× Pace multiplier':<30s} {'×' + str(d['pace_multiplier']):>8s}  (pace: {d['expected_pace']:.1f})")
    print(f"  {'= Matchup component':<30s} {d['matchup_component']:>+8.2f}")
    print(f"  {'+ Home Court Advantage':<30s} {d['hca']:>+8.2f}  (old model: {d['old_hca']:+.2f})")
    print(f"  {'+ Rest adjustment':<30s} {d['rest_adj']:>+8.2f}  (H:{d['h_rest']:+.1f} A:{d['a_rest']:+.1f})")

    tax_note = "⚠️ API FAILED" if d['star_tax_failed'] else ""
    print(f"  {'− Home star tax':<30s} {-d['h_tax']:>+8.2f}  {tax_note}")
    print(f"  {'+ Away star tax':<30s} {d['a_tax']:>+8.2f}  {tax_note}")
    print(f"  {'+ News factor':<30s} {d['news_factor']:>+8.2f}")
    print(f"  {'─'*60}")
    print(f"  {'= FAIR LINE':<30s} {d['fair_line']:>+8.2f}  (old model: {d['old_fair_line']:+.2f})")

    if d['market_line'] is not None:
        print(f"\n  {'Market Line':<30s} {d['market_line']:>+8.2f}")
        print(f"  {'EDGE (new model)':<30s} {d['edge']:>8.2f}")
        print(f"  {'EDGE (old model)':<30s} {d['old_edge']:>8.2f}")
        delta = d['old_edge'] - d['edge']
        direction = "compressed" if delta > 0 else "expanded"
        print(f"  {'Change':<30s} {delta:>+8.2f}  ({direction})")

    # Injuries
    if d['h_injuries'] or d['a_injuries']:
        print(f"\n  ─── Injury Report ───")
        if d['h_injuries']:
            print(f"  {d['home']}:")
            for name, status in d['h_injuries']:
                print(f"    • {name} — {status}")
        if d['a_injuries']:
            print(f"  {d['away']}:")
            for name, status in d['a_injuries']:
                print(f"    • {name} — {status}")

    # News
    if d['news_hits']:
        print(f"\n  ─── News Impacts ───")
        for hit in d['news_hits']:
            print(f"    📰 {hit}")

    # Data quality warnings
    warnings = []
    if d['star_tax_failed']:
        warnings.append("Star Tax API failed — injury impact not reflected in line")
    if d['q_players']:
        warnings.append(f"GTD/Questionable: {', '.join(d['q_players'])}")
    if d['edge'] is not None and d['edge'] > 15:
        warnings.append(f"Edge > 15 — likely capped in UI. Verify matchup manually.")
    if warnings:
        print(f"\n  ─── ⚠️  Warnings ───")
        for w in warnings:
            print(f"    • {w}")

    print()


# ═══════════════════════════════════════════════════════════════════════════════
#  HISTORICAL: Replay Past Bets With Decomposition
# ═══════════════════════════════════════════════════════════════════════════════

def load_all_trackers():
    """Load all bet tracker CSVs."""
    pattern = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bet_tracker_*.csv')
    files = sorted(glob.glob(pattern))
    if not files:
        return pd.DataFrame()
    frames = []
    for f in files:
        df = pd.read_csv(f)
        match_ = re.search(r'bet_tracker_(\d{4}-\d{2}-\d{2})\.csv', f)
        if match_:
            df['Date'] = match_.group(1)
        frames.append(df)
    combined = pd.concat(frames, ignore_index=True)
    combined['Result'] = combined['Result'].astype(str).str.strip().str.upper()
    return combined


def historical_audit():
    """Replay all historical bets with full factor decomposition."""
    df = load_all_trackers()
    if df.empty:
        print("  No bet tracker files found.")
        return

    completed = df[df['Result'].isin(['WIN', 'LOSS', 'PUSH'])]
    if completed.empty:
        print("  No completed bets to audit.")
        return

    print("\n" + "=" * 65)
    print("  📜 HISTORICAL EDGE AUDIT")
    print("=" * 65)
    print(f"  Replaying {len(completed)} completed bets with current model...\n")

    results = []
    for _, row in completed.iterrows():
        away = row['Away']
        home = row['Home']
        try:
            market = float(row['Market'])
        except (ValueError, TypeError):
            continue

        try:
            d = decompose_edge(away, home, market)
            # Use raw edge: prefer Raw_Edge column, else reconstruct from Fair/Market
            if 'Raw_Edge' in row.index and pd.notna(row.get('Raw_Edge')):
                try:
                    old_edge = float(row['Raw_Edge'])
                except (ValueError, TypeError):
                    old_edge = float(row['Edge']) if 'Edge' in row and pd.notna(row['Edge']) else None
            else:
                # Reconstruct raw edge from Fair and Market to avoid using capped Edge
                try:
                    old_edge = round(abs(float(row['Fair']) - float(row['Market'])), 2)
                except (ValueError, TypeError):
                    old_edge = float(row['Edge']) if 'Edge' in row and pd.notna(row['Edge']) else None
            result = row['Result']
            results.append({
                'date': row.get('Date', ''),
                'away': away,
                'home': home,
                'pick': row.get('Pick', ''),
                'result': result,
                'old_edge': old_edge,
                'new_edge': d['edge'],
                'old_fair': d['old_fair_line'],
                'new_fair': d['fair_line'],
                'market': market,
                'regression_impact': d['regression_impact'],
                'hca_change': d['hca'] - d['old_hca'],
                'star_tax_failed': d['star_tax_failed'],
            })
        except Exception as e:
            print(f"  ⚠️  Could not decompose {away} @ {home}: {e}")

    if not results:
        print("  No bets could be replayed.")
        return

    # Summary table
    print(f"  {'Date':<12s} {'Matchup':<30s} {'Pick':<12s} {'Result':<6s} {'OldEdge':>8s} {'NewEdge':>8s} {'Δ':>6s}")
    print(f"  {'─'*84}")
    for r in results:
        matchup = f"{r['away'][:12]} @ {r['home'][:12]}"
        delta = (r['old_edge'] - r['new_edge']) if r['old_edge'] is not None else 0
        marker = "✅" if r['result'] == 'WIN' else "❌"
        print(f"  {r['date']:<12s} {matchup:<30s} {r['pick']:<12s} {marker:<6s} {r['old_edge']:>8.2f} {r['new_edge']:>8.2f} {delta:>+6.2f}")

    # Aggregate stats
    wins = [r for r in results if r['result'] == 'WIN']
    losses = [r for r in results if r['result'] == 'LOSS']
    avg_old_edge = sum(r['old_edge'] for r in results if r['old_edge']) / len(results)
    avg_new_edge = sum(r['new_edge'] for r in results) / len(results)
    avg_compression = avg_old_edge - avg_new_edge

    print(f"\n  ─── Aggregate ───")
    print(f"  Avg Old Edge:    {avg_old_edge:.2f}")
    print(f"  Avg New Edge:    {avg_new_edge:.2f}")
    print(f"  Avg Compression: {avg_compression:+.2f}")

    # Would the new model have changed any picks?
    flipped = [r for r in results if r['new_edge'] < 3 and r['old_edge'] and r['old_edge'] >= 5]
    if flipped:
        print(f"\n  ─── Picks the new model would SKIP (edge dropped below 3) ───")
        for r in flipped:
            marker = "✅" if r['result'] == 'WIN' else "❌"
            print(f"    {marker} {r['away']} @ {r['home']} — Old: {r['old_edge']:.2f} → New: {r['new_edge']:.2f}")

    # Edge tier win rates comparison
    print(f"\n  ─── New Edge Tier Win Rates ───")
    for i, (lo, hi) in enumerate(EDGE_TIERS):
        tier_bets = [r for r in results if lo <= r['new_edge'] < hi]
        if not tier_bets:
            continue
        t_wins = sum(1 for r in tier_bets if r['result'] == 'WIN')
        t_total = len(tier_bets)
        rate = t_wins / t_total * 100
        bar = "█" * int(rate / 5) + "░" * (20 - int(rate / 5))
        print(f"  {EDGE_TIER_LABELS[i]:>6s}  {t_total:>3d} bets  {t_wins}W-{t_total - t_wins}L  {rate:5.1f}%  {bar}")

    print()


# ═══════════════════════════════════════════════════════════════════════════════
#  FACTOR CONTRIBUTION REPORT
# ═══════════════════════════════════════════════════════════════════════════════

def factor_contribution_report():
    """Analyze which factors contribute most to edge across all bets."""
    df = load_all_trackers()
    if df.empty:
        print("  No bet tracker files found.")
        return

    completed = df[df['Result'].isin(['WIN', 'LOSS', 'PUSH'])]
    if completed.empty:
        print("  No completed bets.")
        return

    print("\n" + "=" * 65)
    print("  📊 FACTOR CONTRIBUTION REPORT")
    print("=" * 65)

    factors = {
        'matchup_component': [],
        'regression_impact': [],
        'hca_change': [],
        'rest_adj': [],
        'star_tax_net': [],
        'news_factor': [],
    }
    win_factors = {k: [] for k in factors}
    loss_factors = {k: [] for k in factors}

    for _, row in completed.iterrows():
        try:
            market = float(row['Market'])
            d = decompose_edge(row['Away'], row['Home'], market)
            factors['matchup_component'].append(d['matchup_component'])
            factors['regression_impact'].append(d['regression_impact'])
            factors['hca_change'].append(d['hca'] - d['old_hca'])
            factors['rest_adj'].append(d['rest_adj'])
            factors['star_tax_net'].append(d['a_tax'] - d['h_tax'])
            factors['news_factor'].append(d['news_factor'])

            bucket = win_factors if row['Result'] == 'WIN' else loss_factors
            bucket['matchup_component'].append(d['matchup_component'])
            bucket['regression_impact'].append(d['regression_impact'])
            bucket['hca_change'].append(d['hca'] - d['old_hca'])
            bucket['rest_adj'].append(d['rest_adj'])
            bucket['star_tax_net'].append(d['a_tax'] - d['h_tax'])
            bucket['news_factor'].append(d['news_factor'])
        except Exception:
            continue

    if not factors['matchup_component']:
        print("  Could not decompose any bets.")
        return

    labels = {
        'matchup_component': 'Matchup (OFF/DEF)',
        'regression_impact': 'Regression Adj',
        'hca_change': 'HCA Fix (vs old)',
        'rest_adj': 'Rest Penalty',
        'star_tax_net': 'Star Tax (net)',
        'news_factor': 'News Factor',
    }

    def avg(lst):
        return sum(lst) / len(lst) if lst else 0

    print(f"\n  {'Factor':<22s} {'Avg (All)':>10s} {'Avg (Wins)':>10s} {'Avg (Loss)':>10s} {'|Δ W-L|':>10s}")
    print(f"  {'─'*62}")
    for key in factors:
        a, w, l = avg(factors[key]), avg(win_factors[key]), avg(loss_factors[key])
        delta = abs(w - l)
        print(f"  {labels[key]:<22s} {a:>+10.2f} {w:>+10.2f} {l:>+10.2f} {delta:>10.2f}")

    print(f"\n  Interpretation:")
    print(f"  • Larger |Δ W-L| = factor differentiates winners from losers")
    print(f"  • If Regression Adj is large, the old model was likely over-inflating edges")
    print()


# ═══════════════════════════════════════════════════════════════════════════════
#  MODEL HEALTH CHECK
# ═══════════════════════════════════════════════════════════════════════════════

def model_health_check():
    """Automated diagnostics for model calibration."""
    df = load_all_trackers()
    if df.empty:
        print("  No bet tracker files found.")
        return

    completed = df[df['Result'].isin(['WIN', 'LOSS', 'PUSH'])]
    if completed.empty:
        print("  No completed bets.")
        return

    print("\n" + "=" * 65)
    print("  🩺 MODEL HEALTH CHECK")
    print("=" * 65)

    checks = []
    n = len(completed)

    # Check 1: Sample size
    if n >= 50:
        checks.append(("✅", f"Sample size: {n} bets (statistically meaningful)"))
    elif n >= 20:
        checks.append(("🟡", f"Sample size: {n} bets (minimum viable, need 50+)"))
    else:
        checks.append(("🔴", f"Sample size: {n} bets (too small for conclusions, need 20+)"))

    # Check 2: Overall win rate
    wins = len(completed[completed['Result'] == 'WIN'])
    rate = wins / n * 100
    if rate > 55:
        checks.append(("✅", f"Win rate: {rate:.1f}% (excellent)"))
    elif rate > 52.4:
        checks.append(("✅", f"Win rate: {rate:.1f}% (profitable above 52.4% breakeven)"))
    elif rate > 50:
        checks.append(("🟡", f"Win rate: {rate:.1f}% (positive but below breakeven at -110)"))
    else:
        checks.append(("🔴", f"Win rate: {rate:.1f}% (below 50%, model needs work)"))

    # Check 3: Edge calibration (do higher edges win more?)
    # Use raw edges: prefer Raw_Edge column, else reconstruct from Fair/Market
    def _get_raw_edge(row):
        if 'Raw_Edge' in row.index:
            try:
                val = float(row['Raw_Edge'])
                if val > 0:
                    return val
            except (ValueError, TypeError):
                pass
        try:
            return round(abs(float(row['Fair']) - float(row['Market'])), 2)
        except (ValueError, TypeError, KeyError):
            pass
        try:
            return float(row['Edge'])
        except (ValueError, TypeError):
            return 0.0

    completed_hc = completed.copy()
    completed_hc['_RawEdge'] = completed_hc.apply(_get_raw_edge, axis=1)

    tier_results = []
    for lo, hi in EDGE_TIERS:
        try:
            tier = completed_hc[(completed_hc['_RawEdge'] >= lo) & (completed_hc['_RawEdge'] < hi)]
            if len(tier) >= 2:
                t_wins = len(tier[tier['Result'] == 'WIN'])
                tier_results.append((lo, hi, t_wins / len(tier), len(tier)))
        except (ValueError, TypeError):
            continue

    if len(tier_results) >= 2:
        # Check if higher tiers have higher win rates
        inversions = 0
        for i in range(len(tier_results) - 1):
            if tier_results[i][2] > tier_results[i + 1][2]:
                inversions += 1
        if inversions == 0:
            checks.append(("✅", "Edge calibration: Higher edges → higher win rates"))
        elif inversions <= 1:
            checks.append(("🟡", f"Edge calibration: {inversions} inversion(s) — minor concern"))
        else:
            checks.append(("🔴", f"Edge calibration: {inversions} inversions — edge signal may be unreliable"))

    # Check 4: High-edge performance (uses raw edges)
    try:
        high_edge = completed_hc[completed_hc['_RawEdge'] >= 15]
        if len(high_edge) >= 3:
            he_wins = len(high_edge[high_edge['Result'] == 'WIN'])
            he_rate = he_wins / len(high_edge) * 100
            if he_rate >= 55:
                checks.append(("✅", f"High-edge (≥15) win rate: {he_rate:.0f}% ({he_wins}/{len(high_edge)})"))
            elif he_rate >= 50:
                checks.append(("🟡", f"High-edge (≥15) win rate: {he_rate:.0f}% — not justifying the confidence"))
            else:
                checks.append(("🔴", f"High-edge (≥15) win rate: {he_rate:.0f}% — INVERTED, model overestimates"))
    except (ValueError, TypeError):
        pass

    # Check 5: Star Tax reliability
    star_tax_fail_count = 0
    star_tax_total = 0
    for _, row in completed.iterrows():
        try:
            d = decompose_edge(row['Away'], row['Home'])
            star_tax_total += 1
            if d['star_tax_failed']:
                star_tax_fail_count += 1
        except Exception:
            continue

    if star_tax_total > 0:
        fail_rate = star_tax_fail_count / star_tax_total * 100
        if fail_rate == 0:
            checks.append(("✅", "Star Tax API: All calls successful"))
        elif fail_rate < 30:
            checks.append(("🟡", f"Star Tax API: {fail_rate:.0f}% failure rate ({star_tax_fail_count}/{star_tax_total})"))
        else:
            checks.append(("🔴", f"Star Tax API: {fail_rate:.0f}% failure rate — injury data unreliable"))

    # Check 6: Data freshness
    try:
        with open(CACHE_FILE, 'r') as f:
            cache = json.load(f)
        cache_time = datetime.fromisoformat(cache['timestamp'])
        age_hours = (datetime.now() - cache_time).total_seconds() / 3600
        if age_hours < 12:
            checks.append(("✅", f"Data freshness: {age_hours:.1f}h old"))
        elif age_hours < 24:
            checks.append(("🟡", f"Data freshness: {age_hours:.1f}h old — consider refreshing"))
        else:
            checks.append(("🔴", f"Data freshness: {age_hours:.1f}h old — STALE, refresh before betting"))
    except Exception:
        checks.append(("🔴", "Data freshness: Could not read cache timestamp"))

    # Print results
    passed = sum(1 for c in checks if c[0] == "✅")
    total = len(checks)
    print()
    for icon, msg in checks:
        print(f"  {icon}  {msg}")

    print(f"\n  Score: {passed}/{total} checks passed")
    if passed == total:
        print("  🏆 Model is healthy — keep betting!")
    elif passed >= total * 0.6:
        print("  📊 Model has minor issues — monitor closely")
    else:
        print("  🚨 Model needs attention — review factor decompositions")
    print()


# ═══════════════════════════════════════════════════════════════════════════════
#  INTERACTIVE CLI
# ═══════════════════════════════════════════════════════════════════════════════

def run_analyzer():
    print("\n[SYSTEM] Loading analytics data...")
    calculate_pace_and_ratings()

    try:
        while True:
            print("\n" + "=" * 65)
            print("  🔬 NBA Edge Analyzer — Model Diagnostics Tool")
            print("=" * 65)
            print()
            print("  [1] Live Matchup Decomposition")
            print("  [2] Historical Edge Audit")
            print("  [3] Factor Contribution Report")
            print("  [4] Model Health Check")
            print("  [Q] Quit")
            print()
            choice = input("  Select: ").strip().upper()

            if choice == 'Q':
                print("  Exiting Edge Analyzer.")
                break

            elif choice == '1':
                away = input("  Away team: ").strip()
                home = input("  Home team: ").strip()
                line_in = input("  Market line (e.g., -5.5, or Enter to skip): ").strip()
                market = float(line_in) if line_in else None
                try:
                    d = decompose_edge(away, home, market)
                    print_decomposition(d)
                except Exception as e:
                    print(f"  ❌ Error: {e}")

            elif choice == '2':
                historical_audit()

            elif choice == '3':
                factor_contribution_report()

            elif choice == '4':
                model_health_check()

            else:
                print("  ❌ Invalid option.")

    except KeyboardInterrupt:
        print("\n  [EXIT] Edge Analyzer closed.")


if __name__ == "__main__":
    run_analyzer()
