import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import importlib.util

# Add openalgo root to path
sys.path.append(os.path.join(os.getcwd(), 'openalgo'))
sys.path.append(os.path.join(os.getcwd(), 'openalgo', 'strategies', 'scripts'))
sys.path.append(os.path.join(os.getcwd(), 'openalgo', 'strategies', 'utils'))

# Import SimpleBacktestEngine
try:
    from simple_backtest_engine import SimpleBacktestEngine
except ImportError:
    # Try relative import or path hack
    sys.path.append(os.path.join(os.getcwd(), 'openalgo', 'strategies', 'utils'))
    from simple_backtest_engine import SimpleBacktestEngine

# Import Strategies
try:
    import mcx_crudeoil_smart_breakout_v2 as strat_v2
except ImportError as e:
    print(f"Could not import mcx_crudeoil_smart_breakout_v2: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

def generate_mock_data(days=30, interval="15min"):
    """Generate synthetic OHLCV data with some trends."""
    dates = pd.date_range(end=datetime.now(), periods=days*25, freq=interval)

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

    # Ensure datetime index is named or column exists
    df['datetime'] = df.index

    return df

class MockClient:
    def __init__(self, data):
        self.data = data
        self.api_key = "MOCK"
        self.host = "http://MOCK"

    def history(self, *args, **kwargs):
        return self.data.copy()

def test_v2_logic():
    print("Testing MCX Smart Breakout V2 Logic...")
    mock_data = generate_mock_data(days=10)

    # Test generate_signal
    # We need at least 50 bars
    window = mock_data.iloc[:60]

    # Instantiate strategy wrapper
    # We can call module level generate_signal
    action, score, details = strat_v2.generate_signal(window, client=MockClient(mock_data), symbol="TEST")

    print(f"Signal: {action}, Score: {score}")
    print(f"Details: {details}")

    # Verification
    if 'adx' in details:
        print("PASS: ADX calculation found in details.")
    else:
        print("FAIL: ADX missing from details.")

    if 'atr' in details:
         print("PASS: ATR found in details.")
    else:
         print("FAIL: ATR missing.")

    # Run Full Backtest
    print("\nRunning Full Backtest...")
    engine = SimpleBacktestEngine(initial_capital=100000.0)
    engine.client = MockClient(mock_data)

    start_date = mock_data.index[0].strftime("%Y-%m-%d")
    end_date = mock_data.index[-1].strftime("%Y-%m-%d")

    res = engine.run_backtest(
        strategy_module=strat_v2,
        symbol="TEST",
        exchange="MCX",
        start_date=start_date,
        end_date=end_date,
        interval="15min"
    )

    metrics = res.get('metrics', {})
    print(f"Profit Factor: {metrics.get('profit_factor', 0):.2f}")
    print(f"Total Return: {metrics.get('total_return_pct', 0):.2f}%")
    print(f"Trades: {res.get('total_trades', 0)}")

if __name__ == "__main__":
    test_v2_logic()
