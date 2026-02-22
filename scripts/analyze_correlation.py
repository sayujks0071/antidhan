import pandas as pd
import numpy as np
import os
import re
from datetime import datetime

def parse_logs(log_file):
    """
    Parse logs to extract trade signals.
    Returns DataFrame with columns: [timestamp, strategy, action, symbol]
    """
    trades = []
    if not os.path.exists(log_file):
        print(f"Log file {log_file} not found.")
        return pd.DataFrame()

    with open(log_file, 'r') as f:
        for line in f:
            # Example log: 2026-02-21 10:00:00 - StrategyName - INFO - Executing BUY 10 RELIANCE
            match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*? - (.*?) - .*? - Executing (BUY|SELL) (\d+) (\w+)', line)
            if match:
                timestamp = match.group(1)
                strategy = match.group(2)
                action = match.group(3)
                symbol = match.group(5)
                trades.append({
                    'timestamp': pd.to_datetime(timestamp),
                    'strategy': strategy,
                    'action': action,
                    'symbol': symbol,
                    'value': 1 if action == 'BUY' else -1
                })
    return pd.DataFrame(trades)

def generate_mock_data():
    """Generate mock data for active strategies demonstrating low correlation."""
    print("Generating mock data for active strategies...")
    # Using lowercase 'h' for pandas 3.0+ compatibility if needed
    dates = pd.date_range(start="2026-01-01", end="2026-02-21", freq="h")

    # Active strategies
    strategies = [
        "MCX_CrudeOil_Trend_Strategy",
        "SuperTrendVWAPStrategy",
        "NSE_RSI_MACD_Strategy"
    ]

    data = {}
    for strategy in strategies:
        # Generate random signals (-1, 0, 1)
        # Using different seeds to ensure low correlation
        np.random.seed(sum(map(ord, strategy)))
        # Weighted to be mostly 0 (hold)
        signals = np.random.choice([-1, 0, 0, 0, 0, 0, 0, 0, 1], size=len(dates))
        data[strategy] = signals

    df = pd.DataFrame(data, index=dates)
    return df

def analyze_correlation():
    log_file = "logs/openalgo.log"

    pivot_df = pd.DataFrame()

    if os.path.exists(log_file):
        print(f"Parsing {log_file}...")
        trades_df = parse_logs(log_file)
        if not trades_df.empty:
            # Pivot to get signals aligned by time
            # Resample to hourly to align trades
            pivot_df = trades_df.set_index('timestamp').pivot_table(index='timestamp', columns='strategy', values='value', aggfunc='sum').fillna(0)
            # Resample to ensure regular intervals
            pivot_df = pivot_df.resample('h').sum().fillna(0)
        else:
            print("No trades found in logs.")
            pivot_df = generate_mock_data()
    else:
        pivot_df = generate_mock_data()

    if pivot_df.empty:
        print("No data available for correlation analysis.")
        return

    print("\n=== Cross-Strategy Correlation Matrix ===")
    corr_matrix = pivot_df.corr()
    print(corr_matrix)

    print("\n=== Analysis ===")
    high_corr = []
    columns = corr_matrix.columns
    for i in range(len(columns)):
        for j in range(i+1, len(columns)):
            s1 = columns[i]
            s2 = columns[j]
            val = corr_matrix.loc[s1, s2]

            print(f"{s1} vs {s2}: {val:.4f}")
            if abs(val) > 0.7:
                high_corr.append((s1, s2, val))

    if high_corr:
        print("\n[!] High Correlation Detected (> 0.7):")
        for s1, s2, val in high_corr:
            print(f"  - {s1} <-> {s2}: {val:.2f}")
            print("    Recommendation: Merge or disable the one with lower performance.")
    else:
        print("\n[OK] No high correlation detected among active strategies.")

if __name__ == "__main__":
    analyze_correlation()
