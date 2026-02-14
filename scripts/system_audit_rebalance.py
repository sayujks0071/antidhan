import os
import glob
import json
import re
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys

# Ensure we can import tabulate
try:
    from tabulate import tabulate
except ImportError:
    print("Error: tabulate not installed. Please run: pip install tabulate")
    sys.exit(1)

# Configuration
LOG_DIRS = [
    "logs",
    "openalgo_backup_20260128_164229/logs"
]

def parse_logs():
    """Parse all available logs into a list of trade dictionaries."""
    all_trades = []

    for log_dir in LOG_DIRS:
        if not os.path.exists(log_dir):
            continue

        # 1. Parse JSON Logs (Preferred)
        for filepath in glob.glob(os.path.join(log_dir, "trades_*.json")):
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        strategy_name = os.path.basename(filepath).replace('trades_', '').replace('.json', '')
                        for item in data:
                            item['strategy'] = strategy_name
                            item['source'] = 'json'
                            all_trades.append(item)
            except Exception as e:
                print(f"Error parsing {filepath}: {e}")

        # 2. Parse Text Logs (Fallback/Supplementary)
        # Format: "YYYY-MM-DD HH:MM:SS INFO Strategy: Signal Buy Price"
        # Format: "YYYY-MM-DD HH:MM:SS INFO Strategy: Exiting at Price"

        # We need to track open positions per strategy to pair entries and exits
        open_positions = {} # {strategy: {entry_time, entry_price, direction}}

        for filepath in glob.glob(os.path.join(log_dir, "*.log")):
            try:
                # Deduce strategy name from filename if possible, but reliable way is from log content
                # Filename format: StrategyName_YYYY-MM-DD.log
                filename = os.path.basename(filepath)
                strategy_from_file = filename.split('_')[0]

                with open(filepath, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if not line: continue

                        # Regex for basic components
                        # 2026-01-15 09:27:00 INFO AdvancedMLMomentum: ...
                        match = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO ([^:]+): (.*)", line)
                        if match:
                            timestamp_str, strategy_name, message = match.groups()
                            timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")

                            # Normalize strategy name (sometimes file has it, sometimes log)
                            # In mock logs: "AdvancedMLMomentum" is in log content.

                            if "Signal Buy" in message:
                                # Entry
                                # Signal Buy <Price>
                                try:
                                    parts = message.split()
                                    price = float(parts[-1])
                                    direction = "BUY"

                                    # Store open position
                                    # Assuming FIFO or single position per strategy for simplicity
                                    if strategy_name not in open_positions:
                                        open_positions[strategy_name] = []

                                    open_positions[strategy_name].append({
                                        'entry_time': timestamp,
                                        'entry_price': price,
                                        'direction': direction,
                                        'strategy': strategy_name
                                    })
                                except ValueError:
                                    pass

                            elif "Exiting at" in message:
                                # Exit
                                # Exiting at <Price>
                                try:
                                    parts = message.split()
                                    exit_price = float(parts[-1])

                                    if strategy_name in open_positions and open_positions[strategy_name]:
                                        # Pop the earliest entry (FIFO)
                                        position = open_positions[strategy_name].pop(0)

                                        position['exit_time'] = timestamp
                                        position['exit_price'] = exit_price

                                        # Calculate PnL
                                        # Assuming Quantity = 1 for mock
                                        if position['direction'] == 'BUY':
                                            position['pnl'] = exit_price - position['entry_price']
                                        else:
                                            position['pnl'] = position['entry_price'] - exit_price

                                        all_trades.append(position)
                                except ValueError:
                                    pass

            except Exception as e:
                print(f"Error parsing {filepath}: {e}")

    # Convert to DataFrame
    if not all_trades:
        return pd.DataFrame()

    df = pd.DataFrame(all_trades)

    # Standardize columns
    # Expected: entry_time, exit_time, entry_price, exit_price, direction, quantity, pnl

    # Convert dates
    for col in ['entry_time', 'exit_time']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col])

    return df

def analyze_correlation(df):
    """
    Analyze correlation between strategies.
    Method: Create a time series of positions (1, -1, 0) for each strategy resampled to 15m.
    """
    if df.empty:
        print("No trades found for correlation analysis.")
        return

    print("\n=== Cross-Strategy Correlation Analysis ===")

    # Create a comprehensive time range
    start_time = df['entry_time'].min().floor('15min')
    end_time = df['exit_time'].max().ceil('15min') if 'exit_time' in df.columns and df['exit_time'].notna().any() else datetime.now()

    daterange = pd.date_range(start=start_time, end=end_time, freq='15min')

    strategy_positions = pd.DataFrame(index=daterange)

    strategies = df['strategy'].unique()

    for strategy in strategies:
        strat_trades = df[df['strategy'] == strategy]
        series = pd.Series(0, index=daterange)

        for _, trade in strat_trades.iterrows():
            entry = trade['entry_time']
            exit = trade.get('exit_time', end_time) # Assume open if no exit

            if pd.isna(exit): exit = end_time

            # Round to nearest 15m
            entry_idx = entry.round('15min')
            exit_idx = exit.round('15min')

            direction = 1 if trade.get('direction', 'BUY') == 'BUY' else -1

            # Fill 1 or -1 between entry and exit
            # Handle indexing carefully
            # Using slice assignment requires matching index length or scalar
            # We iterate through time points which is slow but safe, or use boolean mask
            mask = (series.index >= entry_idx) & (series.index <= exit_idx)
            series.loc[mask] = direction

        strategy_positions[strategy] = series

    # Calculate Correlation Matrix
    corr_matrix = strategy_positions.corr()

    print(tabulate(corr_matrix, headers='keys', tablefmt='grid'))

    # Identify high correlation
    high_corr_pairs = []
    columns = corr_matrix.columns
    for i in range(len(columns)):
        for j in range(i+1, len(columns)):
            s1 = columns[i]
            s2 = columns[j]
            val = corr_matrix.iloc[i, j]
            if val > 0.7:
                high_corr_pairs.append((s1, s2, val))

    if high_corr_pairs:
        print("\n[!] High Correlation Detected (> 0.7):")
        for s1, s2, val in high_corr_pairs:
            print(f"  - {s1} <-> {s2}: {val:.2f}")
            print(f"    Recommendation: Merge or disable the one with lower performance.")
    else:
        print("\n[OK] No high correlation detected between strategies.")

    return high_corr_pairs

def analyze_equity_curve(df):
    """
    Reconstruct equity curve and find worst day.
    """
    if df.empty:
        print("No trades found for equity curve analysis.")
        return

    print("\n=== Equity Curve Stress Test ===")

    if 'pnl' not in df.columns:
        print("PnL data missing.")
        return

    # Aggregate by Day
    df['date'] = df['exit_time'].dt.date
    daily_pnl = df.groupby('date')['pnl'].sum()

    if daily_pnl.empty:
        print("No closed trades to analyze PnL.")
        return

    # Cumulative PnL
    equity_curve = daily_pnl.cumsum()

    worst_day = daily_pnl.idxmin()
    worst_loss = daily_pnl.min()

    print(f"Worst Day: {worst_day} (PnL: {worst_loss:.2f})")

    # Root Cause Analysis for Worst Day
    print("\n[Root Cause Analysis]")
    worst_day_trades = df[df['date'] == worst_day]

    strategies_involved = worst_day_trades['strategy'].unique()
    print(f"Strategies involved on {worst_day}: {', '.join(strategies_involved)}")

    # Heuristic checks
    if worst_loss < -500: # Adjusted threshold for mock data
        print("  - Severity: HIGH")
        # Check if it was a gap up/down?
        first_entry = worst_day_trades['entry_time'].min().time()
        market_open_limit = datetime.strptime("09:20", "%H:%M").time()

        if first_entry < market_open_limit:
             print("  - Timing: Early morning losses. Possible Gap Opening failure.")
        else:
             print("  - Timing: Intraday volatility.")
    else:
        print("  - Severity: MODERATE/LOW")

    # Check if multiple strategies lost money
    losers = worst_day_trades[worst_day_trades['pnl'] < 0]['strategy'].unique()
    if len(losers) > 1:
        print("  - Systemic: Multiple strategies failed. Likely market-wide event (Sector/Index crash).")
    else:
        print(f"  - Idiosyncratic: Failure isolated to {losers[0] if len(losers)>0 else 'None'}.")

def main():
    print("Starting System Audit & Rebalance...")
    df = parse_logs()

    if df.empty:
        print("No trade logs found. Skipping analysis.")
        return

    high_corr = analyze_correlation(df)
    analyze_equity_curve(df)

if __name__ == "__main__":
    main()
