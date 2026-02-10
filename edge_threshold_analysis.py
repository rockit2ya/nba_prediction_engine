import pandas as pd

EDGE_THRESHOLDS = [2.5, 5, 7, 10, 12.5, 15]


def analyze_edge_thresholds(csv_path):
    df = pd.read_csv(csv_path)
    df = df[df['Result'].isin(['WIN', 'LOSS'])]
    df['Edge'] = pd.to_numeric(df['Edge'], errors='coerce')
    print("Edge Threshold Analysis:")
    for thresh in EDGE_THRESHOLDS:
        subset = df[df['Edge'] >= thresh]
        if len(subset) == 0:
            continue
        win_rate = (subset['Result'] == 'WIN').mean()
        print(f"Threshold: {thresh:>5} | Bets: {len(subset):>2} | Win Rate: {win_rate:.2%}")
    print("\nRecommendation: Choose the lowest threshold with a win rate near or above your target and a reasonable sample size.")

if __name__ == "__main__":
    analyze_edge_thresholds("bet_tracker_2026-02-09.csv")
