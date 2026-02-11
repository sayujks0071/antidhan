import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Add openalgo root to path
sys.path.append(os.path.join(os.getcwd(), 'openalgo'))
sys.path.append(os.path.join(os.getcwd(), 'openalgo', 'strategies', 'scripts'))
sys.path.append(os.path.join(os.getcwd(), 'openalgo', 'strategies', 'utils'))

# Mock API Client
class MockClient:
    def __init__(self):
        self.api_key = "MOCK"
        self.host = "http://MOCK"

    def history(self, *args, **kwargs):
        return pd.DataFrame() # return empty df if called, but we pass data directly

# Import Strategies
try:
    import advanced_ml_momentum_strategy as ml_strat
    import supertrend_vwap_strategy as st_strat
    import mcx_commodity_momentum_strategy as mcx_strat
    import nse_rsi_bol_trend as nse_strat
    # gap_fade is retired but refactored? Check if active.
    # import gap_fade_strategy as gap_strat
except ImportError as e:
    print(f"Error importing strategies: {e}")
    sys.exit(1)

def generate_mock_data(days=30, interval="15min"):
    """Generate synthetic OHLCV data with some trends."""
    dates = pd.date_range(end=datetime.now(), periods=days*25, freq=interval) # Approx 25 bars per day? 15m * 25 ~ 6h.

    # Random walk with drift
    np.random.seed(42)
    returns = np.random.normal(0.0001, 0.002, len(dates))
    price = 100 * np.cumprod(1 + returns)

    df = pd.DataFrame(index=dates)
    df['close'] = price
    df['open'] = price * (1 + np.random.normal(0, 0.001, len(dates)))
    df['high'] = df[['open', 'close']].max(axis=1) * (1 + abs(np.random.normal(0, 0.001, len(dates))))
    df['low'] = df[['open', 'close']].min(axis=1) * (1 - abs(np.random.normal(0, 0.001, len(dates))))
    df['volume'] = np.random.randint(1000, 100000, len(dates))

    # Add necessary columns for indicators
    df['datetime'] = df.index

    return df

def get_strategy_signals(strategy_module, df):
    signals = []
    # We need to run generate_signal for each bar (simulating live)
    # or just once on the full DF if the strategy supports it?
    # Most strategies take the FULL df and return signal for the LAST bar.
    # So we must iterate.

    # Optimization: iterate last N bars to save time, or skip bars
    # Let's run for last 500 bars
    start_idx = max(50, len(df) - 500)

    client = MockClient()

    for i in range(start_idx, len(df)):
        window = df.iloc[:i+1]
        try:
            # Check if generate_signal supports full df
            # BaseStrategy based ones usually take df and look at last row
            if hasattr(strategy_module, 'generate_signal'):
                action, _, _ = strategy_module.generate_signal(window, client=client, symbol="MOCK")
                if action == 'BUY':
                    signals.append(1)
                elif action == 'SELL':
                    signals.append(-1)
                else:
                    signals.append(0)
            else:
                signals.append(0)
        except Exception as e:
            # print(f"Error in {strategy_module}: {e}")
            signals.append(0)

    return signals

def main():
    print("Generating Mock Data...")
    df = generate_mock_data(days=30)
    print(f"Data generated: {len(df)} bars")

    strategies = {
        'AdvancedML': ml_strat,
        'SuperTrendVWAP': st_strat,
        'MCXMomentum': mcx_strat,
        'NSERsiBol': nse_strat
    }

    results = {}

    print("Running Strategies...")
    for name, module in strategies.items():
        print(f"  Analysing {name}...")
        signals = get_strategy_signals(module, df)
        results[name] = signals

    # Pad to same length if needed (should be same)
    min_len = min(len(s) for s in results.values())
    data = {k: v[:min_len] for k, v in results.items()}

    df_signals = pd.DataFrame(data)

    # Correlation
    print("\nCorrelation Matrix:")
    corr_matrix = df_signals.corr()
    print(corr_matrix)

    print("\nHigh Correlation Pairs (>0.7):")
    found = False
    for i in range(len(corr_matrix.columns)):
        for j in range(i+1, len(corr_matrix.columns)):
            val = corr_matrix.iloc[i, j]
            if abs(val) > 0.7:
                print(f"  {corr_matrix.columns[i]} vs {corr_matrix.columns[j]}: {val:.2f}")
                found = True

    if not found:
        print("  None found.")

if __name__ == "__main__":
    main()
