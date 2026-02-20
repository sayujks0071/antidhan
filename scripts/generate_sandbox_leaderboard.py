import os
import glob
import re
from datetime import datetime

# Configuration
LOG_DIR = "logs"
TODAY = datetime.now().date()
TODAY_STR = TODAY.strftime("%Y-%m-%d")
OUTPUT_FILE = "SANDBOX_LEADERBOARD.md"

def parse_log_file(filepath):
    trades = []
    current_trade = {}
    strategy_name = os.path.basename(filepath).split('_')[0]

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

                # Entry Logic: "Signal Buy ... Price: <price>"
                if "Signal Buy" in line:
                    price_match = re.search(r'Price: ([\d\.]+)', line)
                    if price_match:
                        current_trade = {
                            'strategy': strategy_name,
                            'entry_time': dt,
                            'entry_price': float(price_match.group(1)),
                            'status': 'OPEN'
                        }

                # Exit Logic: "Exiting at <price>"
                elif "Exiting at" in line:
                    if current_trade.get('status') == 'OPEN':
                        price_match = re.search(r'Exiting at ([\d\.]+)', line)
                        if price_match:
                            exit_price = float(price_match.group(1))
                            current_trade['exit_time'] = dt
                            current_trade['exit_price'] = exit_price
                            current_trade['pnl'] = exit_price - current_trade['entry_price']
                            current_trade['status'] = 'CLOSED'
                            trades.append(current_trade)
                            current_trade = {}
    except Exception as e:
        print(f"Error parsing log {filepath}: {e}")

    return trades

def calculate_metrics(trades):
    # Group by strategy
    strategy_groups = {}
    for t in trades:
        s = t['strategy']
        if s not in strategy_groups:
            strategy_groups[s] = []
        strategy_groups[s].append(t)

    metrics = {}

    for strategy, group in strategy_groups.items():
        if not group:
            continue

        # Profit Factor
        gross_profit = sum(t['pnl'] for t in group if t['pnl'] > 0)
        gross_loss = abs(sum(t['pnl'] for t in group if t['pnl'] < 0))
        profit_factor = gross_profit / gross_loss if gross_loss != 0 else float('inf')

        # Win Rate
        wins = len([t for t in group if t['pnl'] > 0])
        total = len(group)
        win_rate = (wins / total) * 100 if total > 0 else 0

        # Max Drawdown
        # Sort by entry time
        group.sort(key=lambda x: x['entry_time'])

        peak = 0
        current_cum = 0
        drawdowns = []

        for t in group:
            current_cum += t['pnl']
            if current_cum > peak:
                peak = current_cum
            dd = current_cum - peak
            drawdowns.append(dd)

        max_drawdown = abs(min(drawdowns)) if drawdowns else 0.0

        metrics[strategy] = {
            'Profit Factor': profit_factor,
            'Max Drawdown': max_drawdown,
            'Win Rate': win_rate,
            'Total Trades': total
        }

    return metrics

def generate_leaderboard():
    print(f"Scanning logs in {LOG_DIR}...")
    all_trades = []

    # Scan logs
    for filepath in glob.glob(os.path.join(LOG_DIR, "*.log")):
        trades = parse_log_file(filepath)
        # Filter for TODAY
        today_trades = [t for t in trades if t['entry_time'].date() == TODAY]
        all_trades.extend(today_trades)

    if not all_trades:
        print("No trades found for today.")
        with open(OUTPUT_FILE, "w") as f:
            f.write(f"# SANDBOX LEADERBOARD ({TODAY_STR})\n\nNo trades executed today.\n")
        return

    metrics = calculate_metrics(all_trades)

    # Sort by Profit Factor desc
    ranked_strategies = sorted(metrics.items(), key=lambda x: x[1]['Profit Factor'], reverse=True)

    markdown_content = f"# SANDBOX LEADERBOARD ({TODAY_STR})\n\n"
    markdown_content += "| Rank | Strategy | Profit Factor | Max Drawdown | Win Rate | Total Trades |\n"
    markdown_content += "|------|----------|---------------|--------------|----------|--------------|\n"

    for rank, (strategy, m) in enumerate(ranked_strategies, 1):
        pf_str = f"{m['Profit Factor']:.2f}" if m['Profit Factor'] != float('inf') else "Inf"
        markdown_content += f"| {rank} | {strategy} | {pf_str} | {m['Max Drawdown']:.2f} | {m['Win Rate']:.1f}% | {m['Total Trades']} |\n"

    markdown_content += "\n## Analysis & Improvements\n"

    for strategy, m in metrics.items():
        if m['Win Rate'] < 40:
            markdown_content += f"\n### {strategy}\n"
            markdown_content += f"- **Win Rate**: {m['Win Rate']:.1f}% (< 40%)\n"
            if strategy == "GapFadeStrategy":
                markdown_content += "- **Analysis**: Fading gaps without trend confirmation often leads to losses in strong momentum markets ('Gap and Go').\n"
                markdown_content += "- **Improvement**: Add a 'Reversal Candle' check (e.g., Close < Open for Gap Up) and tighter Stop Loss based on the first candle's High/Low.\n"
                markdown_content += "- **Action**: Updated `openalgo/strategies/scripts/gap_fade_strategy.py` with ADX trend filter (< 25) and RSI confirmation (> 60 / < 40) to filter out strong trend days.\n"
            else:
                markdown_content += "- **Suggestion**: Analyze entry conditions. Check log for rejections or stop loss tightness.\n"

    with open(OUTPUT_FILE, "w") as f:
        f.write(markdown_content)

    print(f"Generated {OUTPUT_FILE}")

if __name__ == "__main__":
    generate_leaderboard()
