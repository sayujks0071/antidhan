import os
import glob
import re
from datetime import datetime
import pandas as pd

LOG_DIR = "logs"
OUTPUT_FILE = "EQUITY_STRESS_TEST_RESULTS.md"

def parse_logs():
    trades = []
    log_files = glob.glob(os.path.join(LOG_DIR, "*.log"))

    # Regex patterns
    # 2026-02-27 09:15:00 INFO Strategy: Signal Buy NIFTY Price: 24000.00
    # 2026-02-27 10:15:00 INFO Strategy: Exiting at 24100.00

    entry_pattern = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO (.*?): Signal Buy .* Price: ([\d.]+)")
    exit_pattern = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO (.*?): Exiting at ([\d.]+)")

    # We need to match exits to entries. Since logs are simple, we can assume sequential or match by strategy?
    # Mock generator writes entry then exit. But in real logs they are mixed.
    # The mock generator writes entry line then exit line immediately?
    # Let's check the generator logic.
    # f.write(entry...)\n f.write(exit...)
    # Yes, they are paired in the mock generator. But robust parsing should handle them.
    # For now, let's assume lines are sequential for each trade in the mock files.

    for filepath in log_files:
        filename = os.path.basename(filepath)
        # Strategy name is part of filename: Name_Date.log
        strategy_name = filename.split('_')[0]

        with open(filepath, 'r') as f:
            lines = f.readlines()

        current_entry = None

        for line in lines:
            entry_match = entry_pattern.search(line)
            exit_match = exit_pattern.search(line)

            if entry_match:
                current_entry = {
                    "entry_time": datetime.strptime(entry_match.group(1), "%Y-%m-%d %H:%M:%S"),
                    "strategy": entry_match.group(2),
                    "entry_price": float(entry_match.group(3))
                }
            elif exit_match and current_entry:
                exit_time = datetime.strptime(exit_match.group(1), "%Y-%m-%d %H:%M:%S")
                exit_price = float(exit_match.group(3))

                # Calculate PnL (assuming Long only as per generator)
                pnl = exit_price - current_entry["entry_price"]

                trades.append({
                    "date": current_entry["entry_time"].date(),
                    "strategy": strategy_name,
                    "entry_time": current_entry["entry_time"],
                    "exit_time": exit_time,
                    "pnl": pnl
                })
                current_entry = None

    return pd.DataFrame(trades)

def analyze_equity_curve(df):
    if df.empty:
        return "No trades found."

    # Daily PnL
    daily_pnl = df.groupby('date')['pnl'].sum().sort_index()
    cumulative_pnl = daily_pnl.cumsum()

    # Strategy PnL
    strategy_daily_pnl = df.groupby(['date', 'strategy'])['pnl'].sum().unstack(fill_value=0).sort_index()

    # Identify Worst Day
    worst_day_date = daily_pnl.idxmin()
    worst_day_pnl = daily_pnl.min()

    # Identify Best Day
    best_day_date = daily_pnl.idxmax()
    best_day_pnl = daily_pnl.max()

    # Max Drawdown
    rolling_max = cumulative_pnl.cummax()
    drawdown = cumulative_pnl - rolling_max
    max_drawdown = drawdown.min()

    # Report Generation
    with open(OUTPUT_FILE, "w") as f:
        f.write("# Equity Curve Stress Test Results\n\n")

        f.write("## Performance Summary\n")
        f.write(f"- **Total PnL**: {cumulative_pnl.iloc[-1]:.2f}\n")
        f.write(f"- **Best Day**: {best_day_date} (+{best_day_pnl:.2f})\n")
        f.write(f"- **Worst Day**: {worst_day_date} ({worst_day_pnl:.2f})\n")
        f.write(f"- **Max Drawdown**: {max_drawdown:.2f}\n\n")

        f.write("## Worst Day Analysis\n")
        f.write(f"### Date: {worst_day_date}\n")
        f.write(f"**Net PnL**: {worst_day_pnl:.2f}\n\n")

        f.write("#### Strategy Breakdown on Worst Day:\n")
        worst_day_strategies = strategy_daily_pnl.loc[worst_day_date]
        for strategy, pnl in worst_day_strategies.items():
            f.write(f"- **{strategy}**: {pnl:.2f}\n")

        f.write("\n### Root Cause Analysis (Simulated)\n")
        # Heuristic analysis based on strategy behavior
        if "GapFadeStrategy" in worst_day_strategies and worst_day_strategies["GapFadeStrategy"] < -200:
             f.write("- **GapFadeStrategy Failure**: Likely a strong trend day where gaps did not fill. "
                     "The strategy faded a gap that turned into a runaway trend.\n")

        if "SuperTrendVWAP" in worst_day_strategies and worst_day_strategies["SuperTrendVWAP"] < -200:
             f.write("- **SuperTrendVWAP Failure**: Likely a choppy/sideways market causing false breakouts and whipsaws.\n")

        if worst_day_pnl < -1000:
             f.write("- **Systemic Market Crash**: All strategies correlated negatively. High IV crush or gap-down open suspected.\n")

        f.write("\n## Monthly Equity Curve Data\n")
        f.write("| Date | Daily PnL | Cumulative PnL |\n")
        f.write("|------|-----------|----------------|\n")
        for date, pnl in daily_pnl.items():
            cum = cumulative_pnl.loc[date]
            f.write(f"| {date} | {pnl:.2f} | {cum:.2f} |\n")

    print(f"Analysis complete. Report generated at {OUTPUT_FILE}")

def main():
    print("Parsing logs...")
    df = parse_logs()
    print(f"Parsed {len(df)} trades.")
    analyze_equity_curve(df)

if __name__ == "__main__":
    main()
