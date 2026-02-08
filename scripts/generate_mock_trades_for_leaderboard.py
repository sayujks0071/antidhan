import os
import random
from datetime import datetime, timedelta

LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

TODAY = datetime.now().date()
TODAY_STR = TODAY.strftime("%Y-%m-%d")

def generate_log(strategy_name, num_trades, win_rate):
    filepath = os.path.join(LOG_DIR, f"{strategy_name}_{TODAY_STR}.log")

    with open(filepath, "w") as f:
        start_time = datetime.combine(TODAY, datetime.min.time()) + timedelta(hours=9, minutes=15)

        for i in range(num_trades):
            # Advance time
            entry_time = start_time + timedelta(hours=i, minutes=random.randint(0, 30))
            exit_time = entry_time + timedelta(minutes=random.randint(5, 60))

            entry_price = 24000 + random.randint(0, 500)

            # Determine outcome - Deterministic based on index to ensure exact rate
            # For 30%, win if i % 10 < 3 (0, 1, 2 wins; 3..9 losses)
            if strategy_name == "GapFadeStrategy":
                 is_win = (i % 10) < 3
            else:
                 is_win = random.random() < win_rate

            if is_win:
                pnl = random.randint(50, 200)
                exit_price = entry_price + pnl
            else:
                pnl = random.randint(50, 200)
                exit_price = entry_price - pnl

            # Log Entry
            f.write(f"{entry_time.strftime('%Y-%m-%d %H:%M:%S')} INFO {strategy_name}: Signal Buy NIFTY Price: {entry_price:.2f}\n")

            # Log Exit
            f.write(f"{exit_time.strftime('%Y-%m-%d %H:%M:%S')} INFO {strategy_name}: Exiting at {exit_price:.2f}\n")

    print(f"Generated logs for {strategy_name} at {filepath}")

def main():
    print(f"Generating mock logs for date: {TODAY_STR}")

    # SuperTrendVWAP: 10 trades, 60% win rate
    generate_log("SuperTrendVWAP", 10, 0.6)

    # AdvancedMLMomentum: 5 trades, 80% win rate
    generate_log("AdvancedMLMomentum", 5, 0.8)

    # GapFadeStrategy: 10 trades, 30% win rate (FAILING)
    generate_log("GapFadeStrategy", 10, 0.3)

if __name__ == "__main__":
    main()
