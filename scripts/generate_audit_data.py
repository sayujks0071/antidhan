import os
import json
import random
from datetime import datetime, timedelta

LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

def generate_trades(strategy_name, num_trades, win_rate, worst_day=None, correlation_source=None):
    trades = []
    start_date = datetime.now() - timedelta(days=30)

    # Base pattern for correlation
    pattern = []
    for i in range(num_trades):
        pattern.append(random.random())

    for i in range(num_trades):
        # Trade Date
        if correlation_source and i < len(correlation_source):
            # Try to match date of source for correlation
            trade_date = datetime.strptime(correlation_source[i]['entry_time'], "%Y-%m-%d %H:%M:%S")
        else:
            trade_date = start_date + timedelta(days=random.randint(0, 30))

        # Force Worst Day
        if worst_day and i % 5 == 0:
            trade_date = datetime.strptime(worst_day, "%Y-%m-%d").replace(hour=10, minute=0)

        entry_time = trade_date
        exit_time = entry_time + timedelta(minutes=random.randint(15, 120))

        direction = "BUY" if random.random() > 0.5 else "SELL"
        quantity = random.randint(1, 10)
        entry_price = 24000 + random.randint(-500, 500)

        # Outcome
        if worst_day and trade_date.strftime("%Y-%m-%d") == worst_day:
            is_win = False
            pnl = random.randint(-5000, -2000) # Big loss
        else:
            is_win = random.random() < win_rate
            if is_win:
                pnl = random.randint(500, 2000)
            else:
                pnl = random.randint(-1000, -500)

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
    print(f"Generated {len(trades)} trades for {strategy_name}")
    return trades

if __name__ == "__main__":
    worst_day = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
    print(f"Worst Day: {worst_day}")

    # Generate correlated strategies
    t1 = generate_trades("SuperTrendVWAPStrategy", 50, 0.6, worst_day)

    # Highly correlated with SuperTrendVWAPStrategy
    generate_trades("NSE_RSI_MACD_Strategy", 50, 0.55, worst_day, correlation_source=t1)

    # Uncorrelated
    generate_trades("MCX_CrudeOil_Trend_Strategy", 40, 0.45, worst_day)
