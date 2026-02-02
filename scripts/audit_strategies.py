import os
import json
import pandas as pd
from glob import glob

def load_trades(log_dir):
    all_trades = []
    files = glob(os.path.join(log_dir, "trades_*.json"))

    for f in files:
        strategy_name = os.path.basename(f).replace("trades_", "").replace(".json", "")
        try:
            with open(f, 'r') as file:
                data = json.load(file)
                if isinstance(data, list):
                    for trade in data:
                        trade['strategy'] = strategy_name
                        all_trades.append(trade)
        except Exception as e:
            print(f"Error loading {f}: {e}")

    if not all_trades:
        return pd.DataFrame()

    df = pd.DataFrame(all_trades)

    # standardize columns
    if 'entry_time' in df.columns:
        df['entry_time'] = pd.to_datetime(df['entry_time'])
    if 'exit_time' in df.columns:
        df['exit_time'] = pd.to_datetime(df['exit_time'])

    return df

def analyze_correlation(df):
    # Resample PnL to 1H intervals for each strategy
    strategies = df['strategy'].unique()
    pnl_series = {}

    # created a common time index
    start_date = df['entry_time'].min().floor('h')
    end_date = df['exit_time'].max().ceil('h')
    full_range = pd.date_range(start=start_date, end=end_date, freq='h')

    for strategy in strategies:
        strat_df = df[df['strategy'] == strategy].copy()
        strat_df.set_index('exit_time', inplace=True)
        # Sum PnL for each hour
        hourly_pnl = strat_df['pnl'].resample('h').sum().reindex(full_range, fill_value=0)
        pnl_series[strategy] = hourly_pnl

    pnl_df = pd.DataFrame(pnl_series)

    # Calculate correlation
    corr_matrix = pnl_df.corr()
    return corr_matrix

def calculate_calmar(df, initial_capital=100000):
    strategies = df['strategy'].unique()
    results = {}

    for strategy in strategies:
        strat_df = df[df['strategy'] == strategy].copy()
        strat_df = strat_df.sort_values('exit_time')

        # Calculate cumulative PnL
        strat_df['cum_pnl'] = strat_df['pnl'].cumsum()
        strat_df['equity'] = initial_capital + strat_df['cum_pnl']

        # Calculate Max Drawdown
        strat_df['peak'] = strat_df['equity'].cummax()
        strat_df['drawdown'] = (strat_df['equity'] - strat_df['peak']) / strat_df['peak']
        max_dd = strat_df['drawdown'].min()

        # Calculate Annualized Return (approximate)
        days = (strat_df['exit_time'].max() - strat_df['exit_time'].min()).days
        if days < 1: days = 1
        total_return = strat_df['cum_pnl'].iloc[-1] / initial_capital
        annualized_return = total_return * (365 / days)

        calmar = abs(annualized_return / max_dd) if max_dd != 0 else float('inf')

        results[strategy] = {
            'Net PnL': strat_df['cum_pnl'].iloc[-1],
            'Max DD': max_dd,
            'Calmar': calmar
        }

    return pd.DataFrame(results).T

def equity_curve_stress_test(df):
    df = df.sort_values('exit_time')
    daily_pnl = df.groupby(df['exit_time'].dt.date)['pnl'].sum()

    worst_day_date = daily_pnl.idxmin()
    worst_day_loss = daily_pnl.min()

    # Analyze worst day
    worst_day_trades = df[df['exit_time'].dt.date == worst_day_date]

    return daily_pnl, worst_day_date, worst_day_loss, worst_day_trades

import argparse

def main():
    parser = argparse.ArgumentParser(description='Audit Trading Strategies')
    parser.add_argument('--log-dir', type=str, default="openalgo/strategies/logs/", help='Directory containing log files')
    parser.add_argument('--output', type=str, default="audit_results.md", help='Output file for the report')
    args = parser.parse_args()

    log_dir = args.log_dir
    output_file = args.output

    if not os.path.exists(log_dir):
        # Fallback for demonstration/sandbox if default doesn't exist
        fallback = "openalgo_backup_20260128_164229/logs/"
        if os.path.exists(fallback):
             print(f"Default log dir {log_dir} not found. Using backup {fallback} for audit.")
             log_dir = fallback

    print(f"Loading logs from {log_dir}...")
    df = load_trades(log_dir)

    if df.empty:
        print("No trades found.")
        with open(output_file, "w") as f:
            f.write("# Audit Results\n\nNo trades found in logs.")
        return

    with open(output_file, "w") as f:
        f.write("# System Audit & Portfolio Rebalancing Report\n\n")

        # 1. Correlation Analysis
        f.write("## 1. Cross-Strategy Correlation Analysis\n\n")
        corr_matrix = analyze_correlation(df)
        f.write("### Correlation Matrix (Hourly PnL)\n")
        f.write(corr_matrix.to_markdown())
        f.write("\n\n")

        # Check for high correlation
        high_corr = []
        strategies = corr_matrix.columns
        for i in range(len(strategies)):
            for j in range(i+1, len(strategies)):
                val = corr_matrix.iloc[i, j]
                if val > 0.7:
                    high_corr.append((strategies[i], strategies[j], val))

        if high_corr:
            f.write("### ⚠️ High Correlation Alerts (> 0.7)\n")
            for s1, s2, val in high_corr:
                f.write(f"- **{s1}** vs **{s2}**: {val:.2f}\n")
                f.write("  - Action: Consider merging or keeping higher Calmar strategy.\n")
        else:
            f.write("No strategies showed correlation > 0.7.\n")

        f.write("\n")

        # 2. Calmar Ratio
        f.write("## 2. Strategy Performance (Calmar Ratio)\n\n")
        calmar_df = calculate_calmar(df)
        f.write(calmar_df.to_markdown())
        f.write("\n\n")

        # 3. Equity Curve Stress Test
        f.write("## 3. Equity Curve Stress Test\n\n")
        daily_pnl, worst_day, worst_loss, worst_trades = equity_curve_stress_test(df)

        f.write("### Worst Day Analysis\n")
        f.write(f"- **Date:** {worst_day}\n")
        f.write(f"- **Net Loss:** {worst_loss:.2f}\n\n")

        f.write("#### Trades on Worst Day:\n")
        f.write(worst_trades[['strategy', 'symbol', 'direction', 'pnl']].to_markdown())
        f.write("\n\n")

        f.write("#### Root Cause Analysis (Automated)\n")
        # Simple heuristic analysis
        long_loss = worst_trades[worst_trades['direction'] == 'LONG']['pnl'].sum()
        short_loss = worst_trades[worst_trades['direction'] == 'SHORT']['pnl'].sum()

        if long_loss < short_loss and long_loss < 0:
            f.write("- **Primary Driver:** Failed LONG positions (Market Crash/Gap Down?).\n")
        elif short_loss < long_loss and short_loss < 0:
            f.write("- **Primary Driver:** Failed SHORT positions (Short Squeeze/Gap Up?).\n")

        losing_strategies = worst_trades.groupby('strategy')['pnl'].sum().sort_values()
        f.write(f"- **Worst Strategy:** {losing_strategies.index[0]} ({losing_strategies.iloc[0]:.2f})\n")

    print(f"Analysis complete. Results written to {output_file}")

if __name__ == "__main__":
    main()
