import os
import random
from datetime import datetime, timedelta

LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

STRATEGIES = {
    "SuperTrendVWAP": {"trades_per_day": 5, "win_rate": 0.55},
    "AdvancedMLMomentum": {"trades_per_day": 3, "win_rate": 0.75},
    "GapFadeStrategy": {"trades_per_day": 4, "win_rate": 0.35},
}

def generate_log_for_day(date_obj):
    date_str = date_obj.strftime("%Y-%m-%d")

    # Global Market Condition for the day
    is_crash_day = random.random() < 0.05 # 5% chance of crash
    is_trend_day = random.random() < 0.20 # 20% chance of strong trend (good for momentum)

    print(f"Generating logs for {date_str} (Crash: {is_crash_day}, Trend: {is_trend_day})")

    for strategy_name, config in STRATEGIES.items():
        filepath = os.path.join(LOG_DIR, f"{strategy_name}_{date_str}.log")

        daily_win_rate = config["win_rate"]

        if is_crash_day:
            daily_win_rate = max(0.1, daily_win_rate - 0.3)
        elif is_trend_day:
            if "Momentum" in strategy_name or "Trend" in strategy_name:
                daily_win_rate = min(0.9, daily_win_rate + 0.15)
            elif "Fade" in strategy_name: # Mean reversion suffers in strong trend
                daily_win_rate = max(0.1, daily_win_rate - 0.15)

        with open(filepath, "w") as f:
            start_time = datetime.combine(date_obj, datetime.min.time()) + timedelta(hours=9, minutes=15)
            num_trades = max(1, config["trades_per_day"] + random.randint(-1, 2))

            for i in range(num_trades):
                entry_time = start_time + timedelta(hours=i, minutes=random.randint(0, 30))
                if entry_time.hour >= 15: break

                duration = random.randint(5, 60)
                exit_time = entry_time + timedelta(minutes=duration)

                entry_price = 24000 + random.randint(-500, 500)
                is_win = random.random() < daily_win_rate

                if is_win:
                    pnl = random.randint(50, 150)
                    exit_price = entry_price + pnl
                else:
                    pnl = random.randint(50, 200)
                    exit_price = entry_price - pnl

                f.write(f"{entry_time.strftime('%Y-%m-%d %H:%M:%S')} INFO {strategy_name}: Signal Buy NIFTY Price: {entry_price:.2f}\n")
                f.write(f"{exit_time.strftime('%Y-%m-%d %H:%M:%S')} INFO {strategy_name}: Exiting at {exit_price:.2f}\n")

def main():
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=30)

    current_date = start_date
    while current_date <= end_date:
        if current_date.weekday() < 5:
            generate_log_for_day(current_date)
        current_date += timedelta(days=1)

    print(f"Generated 30 days of mock logs in {LOG_DIR}")

if __name__ == "__main__":
    main()
