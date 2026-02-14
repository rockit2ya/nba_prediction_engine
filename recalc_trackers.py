#!/usr/bin/env python3
"""
Recalculate all historical bet tracker fair lines and edges using the NEW model
(with HCA fix, regression to mean, star tax warnings).
Preserves all other columns (results, payouts, notes, etc.).
Originals backed up as .bak files.
"""
import csv
import os
import glob
import re
from nba_analytics import predict_nba_spread
from nba_engine_ui import calculate_kelly

def recalc_file(filepath):
    """Recalculate Fair, Edge, Kelly for a single bet tracker file."""
    with open(filepath, 'r', newline='') as f:
        reader = csv.reader(f)
        rows = list(reader)

    if not rows:
        print(f"  ⚠️  Empty file: {filepath}")
        return

    header = rows[0]
    data_rows = rows[1:]

    # Detect format
    if 'Timestamp' in header:
        # New 18-col format
        fair_idx = header.index('Fair')
        edge_idx = header.index('Edge')
        kelly_idx = header.index('Kelly')
        away_idx = header.index('Away')
        home_idx = header.index('Home')
        market_idx = header.index('Market')
        pick_idx = header.index('Pick')
        conf_idx = header.index('Confidence') if 'Confidence' in header else None
    else:
        # Old 14-col format
        fair_idx = header.index('Fair')
        edge_idx = header.index('Edge')
        kelly_idx = header.index('Kelly')
        away_idx = header.index('Away')
        home_idx = header.index('Home')
        market_idx = header.index('Market')
        pick_idx = header.index('Pick')
        conf_idx = None

    updated = 0
    for row in data_rows:
        away = row[away_idx]
        home = row[home_idx]
        try:
            market = float(row[market_idx])
        except (ValueError, TypeError):
            continue

        try:
            result = predict_nba_spread(away, home)
            fair_line = result[0]
            star_tax_failed = result[4]

            edge = round(abs(fair_line - market), 2)
            kelly = calculate_kelly(market, fair_line)

            # Determine pick recommendation with new model
            recommendation = home if fair_line < market else away

            # Update columns
            row[fair_idx] = str(fair_line)
            row[edge_idx] = str(edge)
            row[kelly_idx] = f"{kelly}%"
            row[pick_idx] = recommendation

            # Update confidence if present
            if conf_idx is not None:
                q_players = result[1]
                if star_tax_failed:
                    row[conf_idx] = "MEDIUM (Star Tax API failed)"
                elif len(q_players) >= 2:
                    row[conf_idx] = "LOW (High Injury Volatility)"
                elif len(q_players) == 1:
                    row[conf_idx] = "MEDIUM"
                else:
                    row[conf_idx] = "HIGH"

            updated += 1
            print(f"  ✅ {away:15s} @ {home:20s} | Fair: {fair_line:>+7.2f} | Edge: {edge:>6.2f} | Pick: {recommendation}")
        except Exception as e:
            print(f"  ⚠️  Could not recalculate {away} @ {home}: {e}")

    # Write back
    with open(filepath, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(data_rows)

    print(f"  → Updated {updated}/{len(data_rows)} bets in {os.path.basename(filepath)}")


def main():
    print("\n" + "=" * 65)
    print("  🔄 RECALCULATING BET TRACKERS WITH NEW MODEL")
    print("=" * 65)
    print("  (Originals backed up as .bak files)\n")

    pattern = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bet_tracker_*.csv')
    files = sorted([f for f in glob.glob(pattern) if not f.endswith('.bak')])

    if not files:
        print("  No bet tracker files found.")
        return

    for filepath in files:
        date_match = re.search(r'bet_tracker_(\d{4}-\d{2}-\d{2})\.csv', filepath)
        date_str = date_match.group(1) if date_match else "unknown"
        print(f"\n  ─── {date_str} ───")
        recalc_file(filepath)

    print(f"\n  ✅ Done! Now run: python post_mortem.py")
    print("  💾 To restore originals: cp bet_tracker_*.csv.bak -> rename .csv")
    print()


if __name__ == "__main__":
    main()
