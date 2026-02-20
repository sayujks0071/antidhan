import os
import glob
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from tabulate import tabulate

LOG_DIR = "logs"

def load_trades():
    all_trades = []

    # Read JSON logs
    for filepath in glob.glob(os.path.join(LOG_DIR, "trades_*.json")):
        try:
            strategy_name = os.path.basename(filepath).replace('trades_', '').replace('.json', '')
            with open(filepath, 'r') as f:
                data = json.load(f)
                for item in data:
                    item['strategy'] = strategy_name
                    all_trades.append(item)
        except Exception as e:
            print(f"Error reading {filepath}: {e}")

    if not all_trades:
        return pd.DataFrame()

    df = pd.DataFrame(all_trades)

    # Ensure datetimes
    df['entry_time'] = pd.to_datetime(df['entry_time'])
    df['exit_time'] = pd.to_datetime(df['exit_time'])
    df['exit_date'] = df['exit_time'].dt.date

    return df

def calculate_calmar_ratio(strategy_trades):
    if strategy_trades.empty:
        return 0.0

    # Aggregate by day
    daily_pnl = strategy_trades.groupby('exit_date')['pnl'].sum()
    if daily_pnl.empty:
        return 0.0

    equity_curve = daily_pnl.cumsum()

    # CAGR (Approximate annualized return based on total return and duration)
    total_return = equity_curve.iloc[-1]
    days = (daily_pnl.index[-1] - daily_pnl.index[0]).days
    if days < 1:
        days = 1

    # Annualize
    cagr = (total_return) * (365.0 / days) # Simplified, usually % return

    # Max Drawdown
    peak = equity_curve.cummax()
    drawdown = equity_curve - peak
    max_drawdown = drawdown.min() # This is a negative number

    if max_drawdown == 0:
        return 999.9 # Infinite

    calmar = abs(cagr / max_drawdown)
    return calmar

def analyze_correlation(df):
    print("\n=== Cross-Strategy Correlation Analysis ===")

    # Resample to daily PnL for correlation
    daily_pnl = df.pivot_table(index='exit_date', columns='strategy', values='pnl', aggfunc='sum').fillna(0)

    if daily_pnl.empty:
        print("No daily PnL data available.")
        return

    corr_matrix = daily_pnl.corr()
    print(tabulate(corr_matrix, headers='keys', tablefmt='grid'))

    # Check for high correlation
    strategies = corr_matrix.columns
    high_corr_pairs = []

    for i in range(len(strategies)):
        for j in range(i+1, len(strategies)):
            val = corr_matrix.iloc[i, j]
            if val > 0.7:
                s1 = strategies[i]
                s2 = strategies[j]
                high_corr_pairs.append((s1, s2, val))

    if high_corr_pairs:
        print("\n[!] High Correlation Detected (> 0.7):")
        for s1, s2, val in high_corr_pairs:
            print(f"  - {s1} <-> {s2}: {val:.2f}")

            # Decide which to keep based on Calmar Ratio
            c1 = calculate_calmar_ratio(df[df['strategy'] == s1])
            c2 = calculate_calmar_ratio(df[df['strategy'] == s2])

            winner = s1 if c1 > c2 else s2
            loser = s2 if c1 > c2 else s1

            print(f"    Recommendation: Keep {winner} (Calmar: {c1:.2f}), Merge/Retire {loser} (Calmar: {c2:.2f})")
    else:
        print("\n[OK] No high correlation detected.")

def analyze_equity_stress_test(df):
    print("\n=== Equity Curve Stress Test ===")

    # Total Daily PnL
    daily_pnl = df.groupby('exit_date')['pnl'].sum()

    if daily_pnl.empty:
        print("No data.")
        return

    equity_curve = daily_pnl.cumsum()

    # Worst Day
    worst_day = daily_pnl.idxmin()
    worst_loss = daily_pnl.min()

    print(f"Worst Day: {worst_day}")
    print(f"Worst Day PnL: {worst_loss:.2f}")

    # Root Cause Analysis
    print("\n[Root Cause Analysis]")
    worst_day_trades = df[df['exit_date'] == worst_day]

    strategies_involved = worst_day_trades['strategy'].unique()
    losing_strategies = worst_day_trades[worst_day_trades['pnl'] < 0]['strategy'].unique()

    print(f"Strategies Trading on {worst_day}: {', '.join(strategies_involved)}")
    print(f"Losing Strategies: {', '.join(losing_strategies)}")

    # Analyze Timing
    # If losses occurred early (first hour), likely Gap Down/Up failure
    market_open = datetime.strptime("09:15", "%H:%M").time()
    gap_cutoff = datetime.strptime("10:15", "%H:%M").time()

    # Extract times
    # We need to filter based on exit_time (realized loss) or entry_time? Usually exit determines PnL realization.
    early_losses = worst_day_trades[
        (worst_day_trades['pnl'] < 0) &
        (worst_day_trades['exit_time'].dt.time < gap_cutoff)
    ]

    if not early_losses.empty:
        print("  - Timing: Significant losses in first hour. Likely failed to handle Gap Opening or Morning Volatility.")
        print("  - Action: Review Gap logic or add 'No Trade Zone' for first 15 mins.")
    else:
        print("  - Timing: Losses distributed throughout the day. Likely Trend Reversal or Chop.")

    # Correlation on Worst Day
    if len(losing_strategies) > 1:
        print("  - Systemic: Multiple strategies failed simultaneously. Indicates High Market Correlation (Risk On/Off event).")
    else:
        print(f"  - Idiosyncratic: Failure isolated to specific strategies.")

def main():
    print("Performing System Audit...")
    df = load_trades()

    if df.empty:
        print("No trades found.")
        return

    analyze_correlation(df)
    analyze_equity_stress_test(df)

if __name__ == "__main__":
    main()
