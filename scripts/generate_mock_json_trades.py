import os
import json
import random
from datetime import datetime, timedelta

LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

def generate_trades(strategy_name, num_trades, win_rate, worst_day=None):
    trades = []
    start_date = datetime.now() - timedelta(days=30)

    for i in range(num_trades):
        # Random date within the last 30 days
        trade_date = start_date + timedelta(days=random.randint(0, 30))

        # If worst_day is specified, force some trades on that day
        if worst_day and i % 5 == 0:  # Force 20% of trades to be on worst day
            trade_date = datetime.strptime(worst_day, "%Y-%m-%d")

        entry_time = trade_date.replace(hour=9, minute=15) + timedelta(minutes=random.randint(0, 300))
        exit_time = entry_time + timedelta(minutes=random.randint(15, 120))

        direction = "BUY" if random.random() > 0.5 else "SELL"
        quantity = random.randint(1, 10)
        entry_price = 24000 + random.randint(-500, 500)

        # Determine Outcome
        if worst_day and trade_date.strftime("%Y-%m-%d") == worst_day:
            is_win = False # Force loss on worst day
        else:
            is_win = random.random() < win_rate

        if is_win:
            pnl = random.randint(500, 2000)
            exit_price = entry_price + (pnl / quantity) if direction == "BUY" else entry_price - (pnl / quantity)
        else:
            pnl = random.randint(-1500, -500)
            exit_price = entry_price + (pnl / quantity) if direction == "BUY" else entry_price - (pnl / quantity)

        trade = {
            "strategy": strategy_name,
            "entry_time": entry_time.strftime("%Y-%m-%d %H:%M:%S"),
            "exit_time": exit_time.strftime("%Y-%m-%d %H:%M:%S"),
            "entry_price": round(entry_price, 2),
            "exit_price": round(exit_price, 2),
            "direction": direction,
            "quantity": quantity,
            "pnl": pnl
        }
        trades.append(trade)

    filepath = os.path.join(LOG_DIR, f"trades_{strategy_name}.json")
    with open(filepath, "w") as f:
        json.dump(trades, f, indent=4)
    print(f"Generated {len(trades)} trades for {strategy_name} in {filepath}")

if __name__ == "__main__":
    worst_day = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
    print(f"Generating mock trades with Worst Day: {worst_day}")

    generate_trades("SuperTrendVWAP", 50, 0.6, worst_day)
    generate_trades("AIHybridStrategy", 40, 0.7, worst_day)
    generate_trades("GapFadeStrategy", 30, 0.4, worst_day)
