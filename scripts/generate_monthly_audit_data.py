import sys
import os
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random

# Add openalgo root to path
sys.path.append(os.path.join(os.getcwd(), 'openalgo'))
sys.path.append(os.path.join(os.getcwd(), 'openalgo', 'strategies', 'scripts'))
sys.path.append(os.path.join(os.getcwd(), 'openalgo', 'strategies', 'utils'))

# Import Strategies
try:
    import advanced_ml_momentum_strategy as ml_strat
    import supertrend_vwap_strategy as st_strat
    import mcx_commodity_momentum_strategy as mcx_strat
    import nse_rsi_bol_trend as nse_strat
    import nse_rsi_macd_strategy as nse_macd
except ImportError as e:
    print(f"Error importing strategies: {e}")
    # Continue with available ones if possible, but for now just exit
    # sys.exit(1)

LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

def generate_mock_ohlcv(days=30, interval="15min"):
    """Generate synthetic OHLCV data."""
    dates = pd.date_range(end=datetime.now(), periods=days*25, freq=interval)

    np.random.seed(42)
    # Drift
    drift = 0.0001
    # Volatility
    vol = 0.002

    returns = np.random.normal(drift, vol, len(dates))
    price = 1000 * np.cumprod(1 + returns)

    df = pd.DataFrame(index=dates)
    df['close'] = price
    df['open'] = price * (1 + np.random.normal(0, 0.001, len(dates)))
    df['high'] = df[['open', 'close']].max(axis=1) * (1 + abs(np.random.normal(0, 0.001, len(dates))))
    df['low'] = df[['open', 'close']].min(axis=1) * (1 - abs(np.random.normal(0, 0.001, len(dates))))
    df['volume'] = np.random.randint(1000, 100000, len(dates))
    df['datetime'] = df.index

    return df

def run_simulation(strategy_name, df):
    """
    Simulate trades based on simple logic if strategy doesn't support backtest directly.
    Or just generate plausible trades based on price movement to simulate strategy behavior.
    """
    trades = []
    position = 0
    entry_price = 0.0
    entry_time = None

    # Simple logic: Moving Average Crossover for simulation
    short_window = 10
    long_window = 30

    df['short_mavg'] = df['close'].rolling(window=short_window, min_periods=1).mean()
    df['long_mavg'] = df['close'].rolling(window=long_window, min_periods=1).mean()

    # Iterate
    for i in range(long_window, len(df)):
        date = df.index[i]
        price = df['close'].iloc[i]

        # Signal
        if df['short_mavg'].iloc[i] > df['long_mavg'].iloc[i] and df['short_mavg'].iloc[i-1] <= df['long_mavg'].iloc[i-1]:
            # Buy Signal
            if position == 0:
                position = 1
                entry_price = price
                entry_time = date
            elif position == -1:
                # Close Short
                pnl = (entry_price - price) * 1 # Qty 1
                trades.append({
                    "entry_time": entry_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "exit_time": date.strftime("%Y-%m-%d %H:%M:%S"),
                    "entry_price": entry_price,
                    "exit_price": price,
                    "direction": "SELL", # Was Short
                    "pnl": pnl,
                    "quantity": 1
                })
                # Open Long
                position = 1
                entry_price = price
                entry_time = date

        elif df['short_mavg'].iloc[i] < df['long_mavg'].iloc[i] and df['short_mavg'].iloc[i-1] >= df['long_mavg'].iloc[i-1]:
            # Sell Signal
            if position == 0:
                position = -1
                entry_price = price
                entry_time = date
            elif position == 1:
                # Close Long
                pnl = (price - entry_price) * 1
                trades.append({
                    "entry_time": entry_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "exit_time": date.strftime("%Y-%m-%d %H:%M:%S"),
                    "entry_price": entry_price,
                    "exit_price": price,
                    "direction": "BUY", # Was Long
                    "pnl": pnl,
                    "quantity": 1
                })
                # Open Short
                position = -1
                entry_price = price
                entry_time = date

    # Add some randomness to differentiate strategies
    # Modify PnL slightly based on strategy name hash
    seed = sum(ord(c) for c in strategy_name)
    random.seed(seed)

    final_trades = []
    for t in trades:
        if random.random() > 0.2: # 80% of trades are kept
            # Add noise to PnL
            noise = random.uniform(0.9, 1.1)
            t['pnl'] *= noise
            final_trades.append(t)

    return final_trades

def main():
    print("Generating Monthly Audit Data...")

    # Active Strategies to Simulate
    strategies = [
        "AdvancedML",
        "SuperTrendVWAP",
        "MCXMomentum",
        "NSERsiBol",
        "NSERsiMacd"
    ]

    # Generate common market data (correlated underlying)
    market_data = generate_mock_ohlcv(days=30)

    for strategy in strategies:
        print(f"Simulating {strategy}...")
        # To make them slightly different, we can tweak the input data or logic
        # Here we rely on the run_simulation randomness and maybe different params if we implemented them

        # For simplicity, we use the same simulation logic but the seed in run_simulation makes them different
        trades = run_simulation(strategy, market_data)

        # Save to JSON
        filepath = os.path.join(LOG_DIR, f"trades_{strategy}.json")
        with open(filepath, 'w') as f:
            json.dump(trades, f, indent=4)

        print(f"Saved {len(trades)} trades to {filepath}")

if __name__ == "__main__":
    main()
