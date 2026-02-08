import os
import random
from datetime import datetime, timedelta

LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

TODAY = datetime.now().date()
STRATEGIES = [
    "AdvancedMLMomentum",
    "SuperTrendVWAP",
    "GapFadeStrategy",
    "MCXSilverMomentum",
    "MCXGoldMomentum",
    "MCXCopperBreakout",
    "NSE_RSI_MACD_TREND",
    "NSE_RSI_BOL_TREND",
    "OptionsRanker",
    "AIHybridReversion"
]

def generate_log(strategy_name, date_obj, win_rate):
    date_str = date_obj.strftime("%Y-%m-%d")
    filepath = os.path.join(LOG_DIR, f"{strategy_name}_{date_str}.log")

    with open(filepath, "w") as f:
        start_time = datetime.combine(date_obj, datetime.min.time()) + timedelta(hours=9, minutes=15)

        num_trades = random.randint(1, 5) # 1-5 trades per day

        for i in range(num_trades):
            # Advance time
            entry_time = start_time + timedelta(hours=i, minutes=random.randint(0, 30))
            exit_time = entry_time + timedelta(minutes=random.randint(5, 60))

            entry_price = 24000 + random.randint(0, 500)

            # Determine outcome
            is_win = random.random() < win_rate

            if is_win:
                pnl = random.randint(50, 200)
                exit_price = entry_price + pnl
                status = "PROFIT"
            else:
                pnl = random.randint(50, 200)
                exit_price = entry_price - pnl
                status = "LOSS"

            # Log Entry
            f.write(f"{entry_time.strftime('%Y-%m-%d %H:%M:%S')} INFO {strategy_name}: Signal Buy NIFTY Price: {entry_price:.2f}\n")

            # Log Exit
            f.write(f"{exit_time.strftime('%Y-%m-%d %H:%M:%S')} INFO {strategy_name}: Exiting at {exit_price:.2f} ({status})\n")

    print(f"Generated logs for {strategy_name} on {date_str} at {filepath}")

def main():
    print(f"Generating mock logs for the past 7 days...")

    for i in range(7):
        date_obj = TODAY - timedelta(days=i)

        # Generate logs for each strategy
        for strategy in STRATEGIES:
            win_rate = 0.5 # Default 50%

            if strategy == "AdvancedMLMomentum":
                win_rate = 0.9 # High win rate for Alpha
            elif strategy == "GapFadeStrategy":
                win_rate = 0.2 # Low win rate for Laggard
            elif strategy == "SuperTrendVWAP":
                win_rate = 0.6

            generate_log(strategy, date_obj, win_rate)

if __name__ == "__main__":
    main()
