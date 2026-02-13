import os
import glob
import pandas as pd
from datetime import datetime

LOG_DIR = "logs"
OUTPUT_FILE = "SANDBOX_LEADERBOARD.md"

def parse_logs():
    trades = []
    today_date = datetime.now().date()

    # Get all log files in logs/
    log_files = glob.glob(os.path.join(LOG_DIR, "*.log"))

    for log_file in log_files:
        # Extract strategy name from filename (StrategyName_YYYY-MM-DD.log)
        filename = os.path.basename(log_file)
        strategy_name = filename.split("_")[0]

        with open(log_file, "r") as f:
            lines = f.readlines()

        current_trade = {}

        for line in lines:
            parts = line.strip().split()
            if len(parts) < 4:
                continue

            timestamp_str = f"{parts[0]} {parts[1]}"
            try:
                timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue

            # Filter for today's trades only
            if timestamp.date() != today_date:
                continue

            message = " ".join(parts[2:])

            if "Signal Buy" in message:
                try:
                    price_str = message.split("Price: ")[1]
                    price = float(price_str)
                    current_trade = {
                        "strategy": strategy_name,
                        "entry_time": timestamp,
                        "entry_price": price,
                        "type": "BUY"
                    }
                except Exception as e:
                    print(f"Error parsing entry line: {line} -> {e}")

            elif "Exiting at" in message:
                if current_trade:
                    try:
                        price_str = message.split("Exiting at ")[1]
                        price = float(price_str)
                        current_trade["exit_time"] = timestamp
                        current_trade["exit_price"] = price

                        # Calculate PnL (assuming LONG for now as per mock generator)
                        pnl = current_trade["exit_price"] - current_trade["entry_price"]
                        current_trade["pnl"] = pnl

                        trades.append(current_trade)
                        current_trade = {}
                    except Exception as e:
                        print(f"Error parsing exit line: {line} -> {e}")

    return trades

def calculate_metrics(trades):
    df = pd.DataFrame(trades)
    if df.empty:
        return pd.DataFrame()

    stats = []

    for strategy, group in df.groupby("strategy"):
        total_trades = len(group)
        wins = group[group["pnl"] > 0]
        losses = group[group["pnl"] <= 0]

        if total_trades > 0:
            win_rate = (len(wins) / total_trades) * 100
        else:
            win_rate = 0.0

        gross_profit = wins["pnl"].sum()
        gross_loss = abs(losses["pnl"].sum())

        profit_factor = gross_profit / gross_loss if gross_loss != 0 else float('inf')

        # Max Drawdown
        group = group.sort_values("exit_time")
        group["cum_pnl"] = group["pnl"].cumsum()
        group["peak"] = group["cum_pnl"].cummax()
        group["drawdown"] = group["peak"] - group["cum_pnl"]
        max_drawdown = group["drawdown"].max()
        if pd.isna(max_drawdown):
            max_drawdown = 0.0

        stats.append({
            "Strategy": strategy,
            "Profit Factor": round(profit_factor, 2),
            "Max Drawdown": round(max_drawdown, 2),
            "Win Rate": f"{win_rate:.1f}%",
            "Total Trades": total_trades,
            "win_rate_val": win_rate # for sorting
        })

    stats_df = pd.DataFrame(stats)
    # Sort by Profit Factor desc, then Win Rate desc
    if not stats_df.empty:
        stats_df = stats_df.sort_values(by=["Profit Factor", "win_rate_val"], ascending=[False, False])
    return stats_df

def generate_markdown(stats_df):
    today = datetime.now().strftime("%Y-%m-%d")
    md = f"# SANDBOX LEADERBOARD ({today})\n\n"

    # Table
    cols = ["Rank", "Strategy", "Profit Factor", "Max Drawdown", "Win Rate", "Total Trades"]
    md += "| " + " | ".join(cols) + " |\n"
    md += "|-" + "-|-".join(["-" * len(c) for c in cols]) + "-|\n"

    rank = 1
    low_win_rate_strategies = []

    for _, row in stats_df.iterrows():
        md += f"| {rank} | {row['Strategy']} | {row['Profit Factor']} | {row['Max Drawdown']} | {row['Win Rate']} | {row['Total Trades']} |\n"

        if row['win_rate_val'] < 40.0:
            low_win_rate_strategies.append(row)
        rank += 1

    md += "\n## Analysis & Improvements\n"

    for row in low_win_rate_strategies:
        strategy = row['Strategy']
        win_rate = row['Win Rate']

        md += f"\n### {strategy}\n"
        md += f"- **Win Rate**: {win_rate} (< 40%)\n"

        if strategy == "GapFadeStrategy":
            md += "- **Analysis**: Fading gaps without trend confirmation often leads to losses in strong momentum markets ('Gap and Go').\n"
            md += "- **Improvement**: Add a 'Reversal Candle' check (e.g., Close < Open for Gap Up) and tighter Stop Loss based on the first candle's High/Low.\n"
        elif strategy == "AdvancedMLMomentum":
            md += "- **Analysis**: Momentum signals may be lagging in choppy markets.\n"
            md += "- **Improvement**: Tighten ROC threshold and add Volatility filter.\n"
        else:
             md += "- **Analysis**: Strategy is underperforming.\n"
             md += "- **Improvement**: Review entry logic and risk management.\n"

    return md

def main():
    trades = parse_logs()
    stats_df = calculate_metrics(trades)

    if not stats_df.empty:
        md_content = generate_markdown(stats_df)
        with open(OUTPUT_FILE, "w") as f:
            f.write(md_content)
        print(f"Generated {OUTPUT_FILE}")
    else:
        print("No trades found in logs.")

if __name__ == "__main__":
    main()
