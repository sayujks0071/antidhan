import os
import random
from datetime import datetime, timedelta

LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# Strategy Configurations
STRATEGIES = {
    "SuperTrendVWAP": {"trades_per_day": 5, "win_rate": 0.6},
    "AdvancedMLMomentum": {"trades_per_day": 3, "win_rate": 0.8},
    "GapFadeStrategy": {"trades_per_day": 5, "win_rate": 0.3},
    "MCX_Gold_Momentum": {"trades_per_day": 2, "win_rate": 0.55},
    # Correlated Strategies
    "NSE_Bollinger_RSI_Strategy": {"trades_per_day": 4, "win_rate": 0.5},
    "NSERsiBolTrendStrategy": {"trades_per_day": 4, "win_rate": 0.5} # Correlated with above
}

def generate_logs_for_period(days=30):
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days)

    current_date = start_date
    while current_date <= end_date:
        # Skip weekends
        if current_date.weekday() < 5:
            generate_logs_for_day(current_date)
        current_date += timedelta(days=1)

def generate_logs_for_day(date_obj):
    date_str = date_obj.strftime("%Y-%m-%d")
    market_open = datetime.combine(date_obj, datetime.min.time()) + timedelta(hours=9, minutes=15)

    # Pre-calculate timestamps for correlated strategies to ensure overlap
    correlated_timestamps = []
    base_trades = STRATEGIES["NSE_Bollinger_RSI_Strategy"]["trades_per_day"]
    for i in range(base_trades):
        entry_time = market_open + timedelta(hours=i, minutes=random.randint(0, 30))
        duration = random.randint(10, 45)
        exit_time = entry_time + timedelta(minutes=duration)
        correlated_timestamps.append((entry_time, exit_time))

    for strategy_name, config in STRATEGIES.items():
        filepath = os.path.join(LOG_DIR, f"{strategy_name}_{date_str}.log")

        trades = []
        num_trades = config["trades_per_day"]
        win_rate = config["win_rate"]

        # Use pre-calculated timestamps for correlated strategies
        if strategy_name in ["NSE_Bollinger_RSI_Strategy", "NSERsiBolTrendStrategy"]:
            # Use the same timestamps (or slightly offset for realism if desired, but here we want high correlation)
            # To simulate >70% correlation, we use the exact same times for most trades
            timestamps = correlated_timestamps
        else:
            timestamps = []
            for i in range(num_trades):
                entry_time = market_open + timedelta(hours=i, minutes=random.randint(0, 50))
                duration = random.randint(5, 60)
                exit_time = entry_time + timedelta(minutes=duration)
                timestamps.append((entry_time, exit_time))

        with open(filepath, "w") as f:
            for i, (entry_time, exit_time) in enumerate(timestamps):
                entry_price = 24000 + random.randint(0, 500)

                # Determine outcome
                is_win = random.random() < win_rate

                # Simulate a "Worst Day" logic: If date is 5 days ago, force losses for some
                is_worst_day = (datetime.now().date() - date_obj).days == 5
                if is_worst_day and strategy_name in ["GapFadeStrategy", "SuperTrendVWAP"]:
                    is_win = False # Force loss
                    pnl = random.randint(200, 500) # Big loss
                else:
                    if is_win:
                        pnl = random.randint(50, 150)
                    else:
                        pnl = random.randint(50, 150)

                exit_price = entry_price + pnl if is_win else entry_price - pnl
                action = "Buy" # Simplified

                # Log Entry
                f.write(f"{entry_time.strftime('%Y-%m-%d %H:%M:%S')} INFO {strategy_name}: Signal {action} {entry_price:.2f}\n")

                # Log Exit with PnL implicitly via price
                # Format: "Exiting at <price>"
                f.write(f"{exit_time.strftime('%Y-%m-%d %H:%M:%S')} INFO {strategy_name}: Exiting at {exit_price:.2f}\n")

                # Also log explicit PnL for easier parsing if needed, but standard logs usually don't have it in this format
                # We'll rely on Entry/Exit price difference

    # print(f"Generated logs for {date_str}")

def main():
    print("Generating comprehensive mock logs for the last 30 days...")
    generate_logs_for_period(30)
    print(f"Logs generated in {LOG_DIR}/")

if __name__ == "__main__":
    main()
