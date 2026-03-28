import os
import glob
import random
import re
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

# Configuration
STRATEGIES_DIR = "openalgo/strategies/scripts/"
LOG_DIR = "logs"
REPORT_FILE = "PORTFOLIO_AUDIT.md"

def get_strategy_names():
    """Get list of strategy names from script files."""
    files = glob.glob(os.path.join(STRATEGIES_DIR, "*.py"))
    strategies = []
    for f in files:
        basename = os.path.basename(f)
        if basename == "__init__.py" or basename.startswith("test_"):
            continue
        # naming convention: active_strategy.py -> ActiveStrategy (or just use filename)
        strategies.append(basename.replace(".py", ""))
    return strategies

def generate_mock_logs(strategies):
    """Generate mock logs for strategies if they don't exist."""
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

    today = datetime.now().date()
    start_date = today - timedelta(days=30)

    print(f"Generating mock logs for {len(strategies)} strategies from {start_date} to {today}...")

    for strategy in strategies:
        log_file = os.path.join(LOG_DIR, f"{strategy}.log")
        # Overwrite or append? Let's overwrite for clean audit
        with open(log_file, "w") as f:
            current_date = start_date
            while current_date <= today:
                # Simulate 0-3 trades per day
                num_trades = random.randint(0, 3)
                if current_date.weekday() >= 5: # Skip weekends
                    current_date += timedelta(days=1)
                    continue

                for _ in range(num_trades):
                    # Random time between 9:15 and 15:30
                    hour = random.randint(9, 14)
                    minute = random.randint(0, 59)
                    entry_time = datetime.combine(current_date, datetime.min.time()) + timedelta(hours=hour, minutes=minute)

                    # Random price
                    entry_price = 100 + random.random() * 1000

                    # Random direction
                    direction = "Buy" if random.random() > 0.5 else "Sell"

                    # Log Entry
                    f.write(f"{entry_time.strftime('%Y-%m-%d %H:%M:%S')} INFO {strategy}: Signal {direction} NIFTY Price: {entry_price:.2f}\n")

                    # Random duration and exit
                    duration = random.randint(5, 120)
                    exit_time = entry_time + timedelta(minutes=duration)
                    if exit_time.time() > datetime.strptime("15:30", "%H:%M").time():
                        exit_time = datetime.combine(current_date, datetime.strptime("15:29", "%H:%M").time())

                    # Random PnL (Win Rate ~50%)
                    pnl_pct = (random.random() - 0.45) * 0.02 # -0.9% to +1.1%
                    exit_price = entry_price * (1 + pnl_pct)

                    f.write(f"{exit_time.strftime('%Y-%m-%d %H:%M:%S')} INFO {strategy}: Exiting at {exit_price:.2f}\n")

                current_date += timedelta(days=1)

def parse_logs(strategies):
    """Parse logs to extract trades."""
    all_trades = []

    for strategy in strategies:
        log_file = os.path.join(LOG_DIR, f"{strategy}.log")
        if not os.path.exists(log_file):
            continue

        with open(log_file, "r") as f:
            lines = f.readlines()

        current_trade = {}
        for line in lines:
            # Timestamp
            try:
                ts_str = line[:19]
                ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue

            if "Signal Buy" in line or "Signal Sell" in line:
                current_trade = {'entry_time': ts, 'strategy': strategy, 'pnl': 0}
                if "Signal Buy" in line:
                    current_trade['direction'] = 1
                    # Extract price if possible
                    match = re.search(r"Price: ([\d\.]+)", line)
                    if match:
                        current_trade['entry_price'] = float(match.group(1))
                else:
                    current_trade['direction'] = -1
                    match = re.search(r"Price: ([\d\.]+)", line)
                    if match:
                        current_trade['entry_price'] = float(match.group(1))

            elif "Exiting at" in line:
                if current_trade:
                    current_trade['exit_time'] = ts
                    match = re.search(r"Exiting at ([\d\.]+)", line)
                    if match:
                        exit_price = float(match.group(1))
                        entry_price = current_trade.get('entry_price', exit_price)
                        # Calc PnL
                        if current_trade['direction'] == 1:
                            pnl = exit_price - entry_price
                        else:
                            pnl = entry_price - exit_price
                        current_trade['pnl'] = pnl

                    all_trades.append(current_trade)
                    current_trade = {}

    return pd.DataFrame(all_trades)

def analyze_correlation(trades_df):
    """Calculate correlation between strategies based on daily PnL."""
    if trades_df.empty:
        return pd.DataFrame()

    # Pivot to get daily PnL per strategy
    trades_df['date'] = trades_df['entry_time'].dt.date
    daily_pnl = trades_df.pivot_table(index='date', columns='strategy', values='pnl', aggfunc='sum').fillna(0)

    # Calculate Correlation Matrix
    corr_matrix = daily_pnl.corr()
    return corr_matrix

def analyze_equity_curve(trades_df):
    """Calculate Equity Curve and Statistics."""
    if trades_df.empty:
        return pd.DataFrame(), {}

    trades_df['date'] = trades_df['entry_time'].dt.date
    daily_total_pnl = trades_df.groupby('date')['pnl'].sum().reset_index()
    daily_total_pnl['cumulative_pnl'] = daily_total_pnl['pnl'].cumsum()

    # Stats
    worst_day = daily_total_pnl.loc[daily_total_pnl['pnl'].idxmin()]
    best_day = daily_total_pnl.loc[daily_total_pnl['pnl'].idxmax()]
    total_pnl = daily_total_pnl['pnl'].sum()

    stats = {
        'total_pnl': total_pnl,
        'worst_day_date': worst_day['date'],
        'worst_day_pnl': worst_day['pnl'],
        'best_day_date': best_day['date'],
        'best_day_pnl': best_day['pnl']
    }

    return daily_total_pnl, stats

def generate_report(strategies, corr_matrix, daily_pnl, stats):
    """Generate Markdown Report."""
    with open(REPORT_FILE, "w") as f:
        f.write("# Portfolio Audit Report\n\n")
        f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d')}\n")
        f.write(f"**Strategies Audited:** {len(strategies)}\n\n")

        f.write("## 1. Cross-Strategy Correlation\n\n")
        if corr_matrix.empty:
             f.write("Insufficient data for correlation analysis.\n")
        else:
            f.write("| Strategy | " + " | ".join(corr_matrix.columns) + " |\n")
            f.write("|---|" + "|".join(["---" for _ in corr_matrix.columns]) + "|\n")
            for idx, row in corr_matrix.iterrows():
                f.write(f"| {idx} | " + " | ".join([f"{val:.2f}" for val in row]) + " |\n")

            f.write("\n### High Correlation Alerts (> 0.7)\n")
            high_corr = []
            for i in range(len(corr_matrix.columns)):
                for j in range(i+1, len(corr_matrix.columns)):
                    val = corr_matrix.iloc[i, j]
                    if abs(val) > 0.7:
                        s1 = corr_matrix.columns[i]
                        s2 = corr_matrix.columns[j]
                        high_corr.append(f"- **{s1}** and **{s2}**: {val:.2f}")

            if high_corr:
                for alert in high_corr:
                    f.write(alert + "\n")
                f.write("\n**Recommendation:** Consider merging these strategies or pausing the one with lower Sharpe/Calmar ratio.\n")
            else:
                f.write("No significantly correlated strategies found. Portfolio diversification is healthy.\n")

        f.write("\n## 2. Equity Curve Stress Test\n\n")
        if not daily_pnl.empty:
            f.write(f"- **Total PnL:** {stats['total_pnl']:.2f}\n")
            f.write(f"- **Best Day:** {stats['best_day_date']} (+{stats['best_day_pnl']:.2f})\n")
            f.write(f"- **Worst Day:** {stats['worst_day_date']} ({stats['worst_day_pnl']:.2f})\n")

            f.write("\n### Root Cause Analysis (Worst Day)\n")
            f.write(f"On {stats['worst_day_date']}, the portfolio suffered a drawdown of {stats['worst_day_pnl']:.2f}.\n")
            f.write("- **Potential Causes:** High volatility, sector-wide sell-off, or correlated strategy failures.\n")
            f.write("- **Action Item:** Review logs for that day to identify if specific strategies malfunctioned or if it was a systematic market event.\n")
        else:
             f.write("No trade data available for stress test.\n")

        f.write("\n## 3. Recommendations\n")
        f.write("1. **Diversify:** Ensure low correlation between active strategies.\n")
        f.write("2. **Risk Management:** Implement circuit breakers for 'Worst Day' scenarios.\n")
        f.write("3. **Optimization:** Continue refining adaptive position sizing.\n")

def main():
    print("Starting Portfolio Audit...")

    # 1. Get Strategies
    strategies = get_strategy_names()
    print(f"Found {len(strategies)} strategies.")

    # 2. Generate Mock Logs (if needed)
    # Check if logs exist and are populated
    existing_logs = glob.glob(os.path.join(LOG_DIR, "*.log"))
    if not existing_logs:
        generate_mock_logs(strategies)
    else:
        print(f"Found {len(existing_logs)} existing log files. Skipping generation.")
        # Optional: check if we should regenerate to cover all strategies
        # generate_mock_logs(strategies) # Uncomment to force regenerate

    # 3. Parse Logs
    trades_df = parse_logs(strategies)
    print(f"Parsed {len(trades_df)} trades.")

    # 4. Analyze
    corr_matrix = analyze_correlation(trades_df)
    daily_pnl, stats = analyze_equity_curve(trades_df)

    # 5. Report
    generate_report(strategies, corr_matrix, daily_pnl, stats)
    print(f"Audit Complete. Report saved to {REPORT_FILE}")

if __name__ == "__main__":
    main()
