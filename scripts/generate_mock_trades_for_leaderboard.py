import os
import random
import json
from datetime import datetime, timedelta

LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

TODAY = datetime.now()

def generate_trades(strategy_name, days=30, win_rate=0.5, correlated_with=None, correlation_strength=0.9):
    trades = []

    # Generate a fixed seed for reproducibility based on strategy name
    random.seed(sum(ord(c) for c in strategy_name))

    start_date = TODAY - timedelta(days=days)

    for i in range(days):
        current_date = start_date + timedelta(days=i)

        # Skip weekends
        if current_date.weekday() >= 5:
            continue

        date_str = current_date.strftime("%Y-%m-%d")

        # Worst Day Scenario: 2026-01-24 (or just the 24th day of the simulated period if hard to hit)
        # Let's pick a specific date relative to TODAY to be the "Worst Day"
        # Say, 5 days ago.
        is_worst_day = (TODAY - current_date).days == 5

        num_trades = random.randint(1, 5)

        for j in range(num_trades):
            entry_time = current_date + timedelta(hours=9 + random.randint(0, 5), minutes=random.randint(0, 59))
            exit_time = entry_time + timedelta(minutes=random.randint(15, 120))

            direction = "BUY" if random.random() > 0.5 else "SELL"
            quantity = random.randint(10, 100)
            entry_price = 1000 + random.randint(0, 200)

            if is_worst_day:
                # Force loss
                pnl = -1 * abs(random.randint(1000, 5000))
                exit_price = entry_price - (pnl / quantity) if direction == "BUY" else entry_price + (pnl / quantity)
            else:
                # Normal logic
                if correlated_with and random.random() < correlation_strength:
                    # Logic to copy correlated strategy would be complex here without shared state.
                    # Instead, we will generate the base strategy first, and then generate the correlated one
                    # by copying the list and modifying slightly.
                    pass
                else:
                    is_win = random.random() < win_rate
                    pnl = random.randint(500, 2000) if is_win else -random.randint(500, 1500)
                    exit_price = entry_price + (pnl / quantity) if direction == "BUY" else entry_price - (pnl / quantity)

            trade = {
                "entry_time": entry_time.strftime("%Y-%m-%d %H:%M:%S"),
                "exit_time": exit_time.strftime("%Y-%m-%d %H:%M:%S"),
                "symbol": "NIFTY",
                "direction": direction,
                "quantity": quantity,
                "entry_price": round(entry_price, 2),
                "exit_price": round(exit_price, 2),
                "pnl": round(pnl, 2),
                "strategy": strategy_name
            }
            trades.append(trade)

    return trades

def save_trades(strategy_name, trades):
    filepath = os.path.join(LOG_DIR, f"trades_{strategy_name}.json")
    with open(filepath, "w") as f:
        json.dump(trades, f, indent=4)
    print(f"Generated {len(trades)} trades for {strategy_name} in {filepath}")

def main():
    print(f"Generating mock logs in {LOG_DIR}...")

    # 1. Independent Strategies
    strategies = [
        ("MCX_Gold_Momentum", 0.55),
        ("NSE_Bollinger_RSI", 0.60),
        ("SuperTrendVWAP", 0.45)
    ]

    generated_data = {}

    for name, win_rate in strategies:
        trades = generate_trades(name, win_rate=win_rate)
        generated_data[name] = trades
        save_trades(name, trades)

    # 2. Correlated Strategies
    # Base: NSE_RSI_MACD_Strategy
    # Correlated: NSE_RSI_MACD_Strategy_V2 (copies Base 90% of time)

    base_name = "NSE_RSI_MACD_Strategy"
    base_trades = generate_trades(base_name, win_rate=0.65)
    save_trades(base_name, base_trades)

    corr_name = "NSE_RSI_MACD_Strategy_V2"
    corr_trades = []

    # Copy trades with slight noise
    for trade in base_trades:
        if random.random() < 0.90: # 90% correlation
            new_trade = trade.copy()
            new_trade["strategy"] = corr_name
            # Slight price diff
            new_trade["entry_price"] += random.uniform(-1, 1)
            new_trade["exit_price"] += random.uniform(-1, 1)
            corr_trades.append(new_trade)
        else:
            # 10% independent random trade? Or just skip?
            # Let's skip to show high overlap but not identical count
            pass

    save_trades(corr_name, corr_trades)

if __name__ == "__main__":
    main()
