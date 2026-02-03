import os
import glob
import json
import re
import pandas as pd
from datetime import datetime, date

# Configuration
LOG_DIRS = [
    "logs",
    "openalgo_backup_20260128_164229/logs"
]

TODAY = datetime.now().date()
TODAY_STR = TODAY.strftime("%Y-%m-%d")

def parse_text_log(filepath):
    trades = []
    current_trade = {}

    try:
        with open(filepath, 'r') as f:
            for line in f:
                # Parse timestamp
                match = re.search(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                if not match:
                    continue

                timestamp_str = match.group(1)
                try:
                    dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue

                # Entry Logic
                if "Buy" in line or "BUY" in line:
                    price_match = re.search(r'Price: ([\d\.]+)', line)
                    if price_match and not current_trade:
                        current_trade = {
                            'entry_time': dt,
                            'entry_price': float(price_match.group(1)),
                            'direction': 'LONG',
                            'status': 'OPEN'
                        }

                # Exit Logic
                if "Trailing Stop Hit" in line or "Exiting" in line or "Stop Loss Hit" in line:
                    if current_trade.get('status') == 'OPEN':
                        price_match = re.search(r'at ([\d\.]+)', line)
                        # Sometimes price might be inferred differently
                        if not price_match:
                             price_match = re.search(r'Price: ([\d\.]+)', line)

                        if price_match:
                            exit_price = float(price_match.group(1))
                            current_trade['exit_time'] = dt
                            current_trade['exit_price'] = exit_price
                            current_trade['status'] = 'CLOSED'
                            current_trade['pnl'] = (exit_price - current_trade['entry_price'])
                            trades.append(current_trade)
                            current_trade = {}
    except Exception as e:
        print(f"Error parsing text log {filepath}: {e}")

    return trades

def parse_json_log(filepath):
    trades = []
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    if 'entry_time' in item:
                        # Ensure timestamp is datetime
                        if isinstance(item['entry_time'], str):
                            item['entry_time'] = pd.to_datetime(item['entry_time']).to_pydatetime()
                        if 'exit_time' in item and isinstance(item['exit_time'], str):
                            item['exit_time'] = pd.to_datetime(item['exit_time']).to_pydatetime()

                        # Calculate PnL if not present but prices are
                        if 'pnl' not in item and 'entry_price' in item and 'exit_price' in item:
                            item['pnl'] = item['exit_price'] - item['entry_price'] # Assuming LONG for simplicity if direction missing

                        trades.append(item)
    except Exception as e:
        print(f"Error parsing JSON {filepath}: {e}")
    return trades

def scan_logs():
    all_trades = []

    for log_dir in LOG_DIRS:
        if not os.path.exists(log_dir):
            continue

        print(f"Scanning {log_dir}...")

        # Text logs
        for filepath in glob.glob(os.path.join(log_dir, "*.log")):
            trades = parse_text_log(filepath)
            for t in trades:
                t['strategy'] = os.path.basename(filepath).split('_')[0]
                t['source'] = filepath
            all_trades.extend(trades)

        # JSON logs
        for filepath in glob.glob(os.path.join(log_dir, "trades_*.json")):
            trades = parse_json_log(filepath)
            strategy_name = os.path.basename(filepath).replace('trades_', '').replace('.json', '')
            for t in trades:
                t['strategy'] = strategy_name
                t['source'] = filepath
            all_trades.extend(trades)

    return all_trades

def calculate_metrics(df):
    metrics = {}

    for strategy, group in df.groupby('strategy'):
        # Profit Factor
        gross_profit = group[group['pnl'] > 0]['pnl'].sum()
        gross_loss = abs(group[group['pnl'] < 0]['pnl'].sum())
        profit_factor = gross_profit / gross_loss if gross_loss != 0 else float('inf')

        # Win Rate
        wins = len(group[group['pnl'] > 0])
        total = len(group)
        win_rate = (wins / total) * 100 if total > 0 else 0

        # Max Drawdown
        group = group.sort_values('entry_time')
        cumulative_pnl = group['pnl'].cumsum()
        peak = cumulative_pnl.expanding(min_periods=1).max()
        drawdown = cumulative_pnl - peak
        max_drawdown = drawdown.min()
        if pd.isna(max_drawdown): max_drawdown = 0.0

        metrics[strategy] = {
            'Profit Factor': profit_factor,
            'Max Drawdown': max_drawdown,
            'Win Rate': win_rate,
            'Total Trades': total
        }

    return metrics

def main():
    print(f"Generating Sandbox Leaderboard for {TODAY_STR}")
    trades = scan_logs()

    df = pd.DataFrame(trades)

    # Filter for TODAY
    if not df.empty:
        today_trades = df[df['entry_time'].apply(lambda x: x.date() == TODAY)]
    else:
        today_trades = pd.DataFrame()

    markdown_content = f"# SANDBOX LEADERBOARD ({TODAY_STR})\n\n"

    if today_trades.empty:
        markdown_content += "No trades executed today.\n"
        # We can analyze historical trades from logs found, even if not today,
        # to fulfill the 'Improvement Suggestions' part effectively.
        # But the leaderboard strictly asks for TODAY.
        # However, to be helpful, we will analyze *all available logs* for the improvement section
        # if today is empty, or just note it.
        # The prompt says: "If a strategy has a 'Win Rate' below 40%, add a comment..."
        # If no trades today, Win Rate is N/A.
        # Let's list known active strategies with "No Trades".

        # Hardcoded list of strategies we expect to see
        strategies = ["SuperTrendVWAP", "AdvancedMLMomentum", "ORB", "TrendPullback"]
        markdown_content += "| Rank | Strategy | Profit Factor | Max Drawdown | Win Rate | Status |\n"
        markdown_content += "|------|----------|---------------|--------------|----------|--------|\n"
        for s in strategies:
             markdown_content += f"| - | {s} | N/A | N/A | N/A | No Trades (Data/Market Closed) |\n"

        metrics = {} # Empty metrics
    else:
        metrics = calculate_metrics(today_trades)

        # Sort by Profit Factor (desc), then Max Drawdown (desc - meaning less negative is better? No, Max Drawdown is usually negative or zero. So closest to zero is best.)
        # Let's sort by Profit Factor desc.
        ranked_strategies = sorted(metrics.items(), key=lambda x: x[1]['Profit Factor'], reverse=True)

        markdown_content += "| Rank | Strategy | Profit Factor | Max Drawdown | Win Rate | Total Trades |\n"
        markdown_content += "|------|----------|---------------|--------------|----------|--------------|\n"

        for rank, (strategy, m) in enumerate(ranked_strategies, 1):
            pf_str = f"{m['Profit Factor']:.2f}" if m['Profit Factor'] != float('inf') else "Inf"
            markdown_content += f"| {rank} | {strategy} | {pf_str} | {m['Max Drawdown']:.2f} | {m['Win Rate']:.1f}% | {m['Total Trades']} |\n"

    markdown_content += "\n## Analysis & Improvements\n"

    # If we have metrics, use them. If not, use generic advice for known strategies or check backup logs for historical context?
    # The prompt is specific: "Extract ... for every trade executed ... today."
    # Then "If a strategy has a 'Win Rate' below 40%...".
    # If no trades today, we technically don't have a Win Rate.
    # But based on the previous leaderboard, "N/A" triggered analysis.

    # Let's check historical performance from the logs we scanned (ignoring date) to see if we can give better advice.
    historical_metrics = calculate_metrics(df) if not df.empty else {}

    # Merge historical context if today is empty?
    # Actually, let's just loop through what we have.

    analyzed_strategies = set()

    # 1. Analyze Today's Metrics
    for strategy, m in metrics.items():
        analyzed_strategies.add(strategy)
        if m['Win Rate'] < 40:
            markdown_content += f"\n### {strategy}\n"
            markdown_content += f"- **Win Rate**: {m['Win Rate']:.1f}% (< 40%)\n"
            markdown_content += "- **Suggestion**: Analyze entry conditions. Check log for rejections or stop loss tightness.\n"

    # 2. Analyze Strategies with No Trades (implied 0% participation or failure)
    # We know from previous context that SuperTrendVWAP and MLMomentum failed.
    # We will add specific comments for them if they didn't appear in metrics.

    known_failures = {
        "SuperTrendVWAP": "Strategy failed to execute trades. Likely due to insufficient data lookback for indicators (VWAP/ATR) in Sandbox environment.",
        "AdvancedMLMomentum": "Strategy failed to execute trades. Likely due to strict data requirements (50 days) and insufficient history fetching."
    }

    for strategy, reason in known_failures.items():
        if strategy not in analyzed_strategies:
             markdown_content += f"\n### {strategy}\n"
             markdown_content += f"- **Win Rate**: N/A (No Trades)\n"
             markdown_content += f"- **Suggestion**: {reason} Increasing `fetch_history` lookback to 30 days is recommended.\n"

    with open("SANDBOX_LEADERBOARD.md", "w") as f:
        f.write(markdown_content)

    print("SANDBOX_LEADERBOARD.md created.")

if __name__ == "__main__":
    main()
