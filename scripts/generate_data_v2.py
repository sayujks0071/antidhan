import os
import random
from datetime import datetime, timedelta

LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

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
        num_trades = random.randint(1, 5)

        for i in range(num_trades):
            entry_time = start_time + timedelta(hours=i, minutes=random.randint(0, 30))
            exit_time = entry_time + timedelta(minutes=random.randint(5, 60))
            entry_price = 24000 + random.randint(0, 500)

            is_win = random.random() < win_rate
            if is_win:
                pnl = random.randint(50, 200)
                exit_price = entry_price + pnl
                status = "PROFIT"
            else:
                pnl = random.randint(50, 200)
                exit_price = entry_price - pnl
                status = "LOSS"

            f.write(f"{entry_time.strftime('%Y-%m-%d %H:%M:%S')} INFO {strategy_name}: Signal Buy NIFTY Price: {entry_price:.2f}\n")
            f.write(f"{exit_time.strftime('%Y-%m-%d %H:%M:%S')} INFO {strategy_name}: Exiting at {exit_price:.2f} ({status})\n")

    print(f"Generated {filepath}")

def main():
    print("Generating logs...")
    today = datetime.now().date()
    for i in range(7):
        date_obj = today - timedelta(days=i)
        for strategy in STRATEGIES:
            win_rate = 0.5
            if strategy == "AdvancedMLMomentum": win_rate = 0.95
            if strategy == "GapFadeStrategy": win_rate = 0.1
            if strategy == "SuperTrendVWAP": win_rate = 0.6

            generate_log(strategy, date_obj, win_rate)

if __name__ == "__main__":
    main()
