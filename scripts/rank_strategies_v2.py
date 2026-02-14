import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import importlib.util
import inspect

# Add openalgo root to path
sys.path.append(os.path.join(os.getcwd(), 'openalgo'))
sys.path.append(os.path.join(os.getcwd(), 'openalgo', 'strategies', 'scripts'))
sys.path.append(os.path.join(os.getcwd(), 'openalgo', 'strategies', 'utils'))

# Import SimpleBacktestEngine
from simple_backtest_engine import SimpleBacktestEngine

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

def load_strategies():
    strategies = {}
    strategies_dir = os.path.join(os.getcwd(), 'openalgo', 'strategies', 'scripts')

    for filename in os.listdir(strategies_dir):
        if filename.endswith('.py') and filename != '__init__.py':
            module_name = filename[:-3]
            file_path = os.path.join(strategies_dir, filename)

            try:
                spec = importlib.util.spec_from_file_location(module_name, file_path)
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)

                # Check if it has generate_signal
                if hasattr(module, 'generate_signal'):
                    strategies[module_name] = module
                else:
                    # Check for class based strategy
                    for name, obj in inspect.getmembers(module):
                        if inspect.isclass(obj) and hasattr(obj, 'generate_signal'):
                            # Instantiate if needed or use class method?
                            # Most openalgo strategies seem to use module-level generate_signal or static/class method
                            # If it's a class inheriting BaseStrategy, it likely has generate_signal
                            strategies[module_name] = obj() # Instantiate
                            break
            except Exception as e:
                print(f"Skipping {filename}: {e}")

    return strategies

def main():
    print("Generating Mock Data...")
    mock_data = generate_mock_data(days=30)

    strategies = load_strategies()
    print(f"Found {len(strategies)} strategies.")

    results = []
    initial_capital = 1000000.0

    for name, module in strategies.items():
        print(f"Backtesting {name}...")
        engine = SimpleBacktestEngine(initial_capital=initial_capital)
        engine.client = MockClient(mock_data)

        start_date = mock_data.index[0].strftime("%Y-%m-%d")
        end_date = mock_data.index[-1].strftime("%Y-%m-%d")

        try:
            res = engine.run_backtest(
                strategy_module=module,
                symbol="MOCK",
                exchange="NSE",
                start_date=start_date,
                end_date=end_date,
                interval="15min"
            )

            metrics = res.get('metrics', {})
            results.append({
                'name': name,
                'profit_factor': metrics.get('profit_factor', 0),
                'total_return_pct': metrics.get('total_return_pct', 0),
                'max_drawdown_pct': metrics.get('max_drawdown_pct', 0),
                'win_rate': metrics.get('win_rate', 0),
                'trades': res.get('total_trades', 0)
            })

        except Exception as e:
            print(f"Error backtesting {name}: {e}")

    # Sort by Profit Factor
    results.sort(key=lambda x: x['profit_factor'], reverse=True)

    print("\nRANKING:")
    print(f"{'Rank':<5} {'Strategy':<35} {'PF':<10} {'Return %':<10} {'DD %':<10} {'Trades':<10}")
    print("-" * 85)

    for i, res in enumerate(results):
        print(f"{i+1:<5} {res['name']:<35} {res['profit_factor']:<10.2f} {res['total_return_pct']:<10.2f} {res['max_drawdown_pct']:<10.2f} {res['trades']:<10}")

    if not results:
        return

    alpha = results[0]
    laggard = results[-1]

    print(f"\nAlpha: {alpha['name']} (PF: {alpha['profit_factor']:.2f})")
    print(f"Laggard: {laggard['name']} (PF: {laggard['profit_factor']:.2f})")

    # Save to file for next steps to read
    with open("STRATEGY_RANKING.txt", "w") as f:
        f.write(f"Alpha:{alpha['name']}\n")
        f.write(f"Laggard:{laggard['name']}\n")
        f.write(f"Laggard_PF:{laggard['profit_factor']}\n")

        # Write full table
        f.write("\nTable:\n")
        for res in results:
             f.write(f"{res['name']},{res['profit_factor']},{res['max_drawdown_pct']}\n")

if __name__ == "__main__":
    main()
