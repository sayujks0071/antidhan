import sys
import os
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import importlib.util

# Add openalgo root to path
project_root = os.getcwd()
if 'openalgo' not in os.listdir(project_root):
    project_root = os.path.dirname(project_root)

sys.path.append(os.path.join(project_root))
sys.path.append(os.path.join(project_root, 'openalgo'))
sys.path.append(os.path.join(project_root, 'openalgo', 'strategies', 'scripts'))
sys.path.append(os.path.join(project_root, 'openalgo', 'strategies', 'utils'))

# Import SimpleBacktestEngine
from simple_backtest_engine import SimpleBacktestEngine

# Mock API Client
class MockClient:
    def __init__(self, data_map):
        self.data_map = data_map # Key: symbol, Value: df
        self.api_key = "MOCK"
        self.host = "http://MOCK"

    def history(self, symbol, *args, **kwargs):
        # Return specific data for symbol if available, else default mock
        if symbol in self.data_map:
            return self.data_map[symbol].copy()
        # Fallback to generic mock if not found
        return self.data_map.get('DEFAULT', pd.DataFrame()).copy()

def load_active_strategies():
    config_path = os.path.join(project_root, 'openalgo', 'strategies', 'strategy_configs.json')
    if not os.path.exists(config_path):
        print(f"Config not found at {config_path}")
        return {}

    with open(config_path, 'r') as f:
        configs = json.load(f)

    strategies = {}
    for name, config in configs.items():
        # if not config.get('is_running') and not config.get('schedule_enabled'):
        #     continue

        file_path = config.get('file_path')
        if not file_path: continue

        full_path = os.path.join(project_root, 'openalgo', file_path)
        if not os.path.exists(full_path):
            # Try finding it relative to strategy root
            alt_path = os.path.join(project_root, 'openalgo', 'strategies', 'scripts', os.path.basename(file_path))
            if os.path.exists(alt_path):
                full_path = alt_path
            else:
                print(f"Strategy file not found: {full_path}")
                continue

        try:
            spec = importlib.util.spec_from_file_location(name, full_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            strategies[name] = module
        except Exception as e:
            print(f"Failed to load {name}: {e}")

    return strategies

def generate_mock_data(days=30, interval="15m", symbol="DEFAULT"):
    """Generate synthetic OHLCV data with some trends."""
    if interval.endswith('m'):
        freq = interval.replace('m', 'min')
    else:
        freq = interval

    dates = pd.date_range(end=datetime.now(), periods=days*25, freq=freq)

    # Random walk with drift
    np.random.seed(hash(symbol) % 2**32)
    returns = np.random.normal(0.0001, 0.002, len(dates))
    price = 1000 * np.cumprod(1 + returns)

    df = pd.DataFrame(index=dates)
    df['close'] = price
    df['open'] = price * (1 + np.random.normal(0, 0.001, len(dates)))
    df['high'] = df[['open', 'close']].max(axis=1) * (1 + abs(np.random.normal(0, 0.001, len(dates))))
    df['low'] = df[['open', 'close']].min(axis=1) * (1 - abs(np.random.normal(0, 0.001, len(dates))))
    df['volume'] = np.random.randint(1000, 100000, len(dates))

    # Ensure datetime index is named or column exists
    df['datetime'] = df.index

    return df

def main():
    print("Loading Active Strategies...")
    strategies = load_active_strategies()
    print(f"Loaded {len(strategies)} strategies.")

    portfolio_equity = {} # Key: date, Value: equity
    initial_capital_per_strat = 1000000.0

    # Pre-generate data for likely symbols
    # This is a simplification. Ideally, we inspect strategy to find symbol.
    data_map = {
        'DEFAULT': generate_mock_data(days=60, symbol='DEFAULT')
    }

    results = {}

    for name, module in strategies.items():
        print(f"Backtesting {name}...")

        # Determine symbol from module if possible
        symbol = "MOCK"
        if hasattr(module, 'SYMBOL'):
            symbol = module.SYMBOL

        # Ensure we have data for this symbol (or use default)
        if symbol not in data_map:
            data_map[symbol] = generate_mock_data(days=60, symbol=symbol)

        engine = SimpleBacktestEngine(initial_capital=initial_capital_per_strat)
        # Inject Mock Client
        engine.client = MockClient(data_map)

        # Run backtest
        start_date = data_map[symbol].index[0].strftime("%Y-%m-%d")
        end_date = data_map[symbol].index[-1].strftime("%Y-%m-%d")

        try:
            # Check if strategy has generate_signal at module level or as class method wrapper
            if not hasattr(module, 'generate_signal'):
                # Try finding class
                found = False
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if isinstance(attr, type) and attr_name.endswith('Strategy'):
                        # Wrap class method
                        def wrapper(df, client=None, symbol=None):
                            # Instantiate with mock client
                            strat = attr(symbol=symbol, api_key="MOCK", host="http://MOCK", client=client)
                            # Suppress logging
                            import logging
                            strat.logger.handlers = []
                            strat.logger.addHandler(logging.NullHandler())

                            # Adapt return to (signal, qty, details)
                            res = strat.get_signal(df)
                            if isinstance(res, str):
                                return res, 1.0, {}
                            elif isinstance(res, tuple):
                                if len(res) == 2: return res[0], res[1], {}
                                return res
                            return "HOLD", 0.0, {}

                        module.generate_signal = wrapper
                        found = True
                        break

                if not found:
                    print(f"Skipping {name}: No generate_signal or Strategy class found.")
                    continue

            res = engine.run_backtest(
                strategy_module=module,
                symbol=symbol,
                exchange="NSE", # Default
                start_date=start_date,
                end_date=end_date,
                interval="15m"
            )

            if 'error' in res:
                print(f"  Error: {res['error']}")
                continue

            results[name] = res

            # Aggregate Equity Curve
            # res['equity_curve'] is list of (timestamp_str, equity_float)
            for ts_str, equity in res['equity_curve']:
                try:
                    ts = pd.to_datetime(ts_str).date()
                except:
                    continue

                if ts not in portfolio_equity:
                    portfolio_equity[ts] = 0
                portfolio_equity[ts] += (equity - initial_capital_per_strat) # Add PnL

        except Exception as e:
            print(f"Error backtesting {name}: {e}")
            # import traceback
            # traceback.print_exc()

    if not results:
        print("No successful backtests.")
        return

    # Total Portfolio Value (Assuming sum of initial capitals + PnL)
    total_initial = len(results) * initial_capital_per_strat

    # Sort dates
    sorted_dates = sorted(portfolio_equity.keys())

    daily_equity = []
    for d in sorted_dates:
        pnl = portfolio_equity[d]
        daily_equity.append({'date': d, 'equity': total_initial + pnl, 'pnl': pnl})

    df_equity = pd.DataFrame(daily_equity)

    if df_equity.empty:
        print("No equity curve generated.")
        return

    # Calculate Drawdowns
    df_equity['peak'] = df_equity['equity'].cummax()
    df_equity['drawdown'] = df_equity['equity'] - df_equity['peak']
    df_equity['drawdown_pct'] = (df_equity['drawdown'] / df_equity['peak']) * 100

    worst_day_row = df_equity.loc[df_equity['pnl'].idxmin()]
    max_dd_row = df_equity.loc[df_equity['drawdown_pct'].idxmin()]

    print("\n" + "="*50)
    print("STRESS TEST RESULTS")
    print("="*50)
    print(f"Strategies Tested: {len(results)}")
    print(f"Total Return: {df_equity.iloc[-1]['equity'] - total_initial:.2f}")
    print(f"Worst Day: {worst_day_row['date']} (PnL: {worst_day_row['pnl']:.2f})")
    print(f"Max Drawdown: {max_dd_row['drawdown_pct']:.2f}% on {max_dd_row['date']}")

    # Save Report
    with open("EQUITY_STRESS_TEST_RESULTS.md", "w") as f:
        f.write("# Equity Curve Stress Test Report\n\n")
        f.write(f"**Date**: {datetime.now().strftime('%Y-%m-%d')}\n")
        f.write(f"**Strategies Included**: {len(results)}\n\n")

        f.write("## Portfolio Performance\n")
        f.write(f"- **Total Return**: {df_equity.iloc[-1]['equity'] - total_initial:.2f}\n")
        f.write(f"- **Worst Day**: {worst_day_row['date']} (PnL: {worst_day_row['pnl']:.2f})\n")
        f.write(f"- **Max Drawdown**: {max_dd_row['drawdown_pct']:.2f}% on {max_dd_row['date']}\n\n")

        f.write("## Strategy Performance\n")
        f.write("| Strategy | Trades | Win Rate | Profit Factor | Total Return |\n")
        f.write("|----------|--------|----------|---------------|--------------|\n")

        for name, res in results.items():
            metrics = res.get('metrics', {})
            f.write(f"| {name} | {res.get('total_trades', 0)} | {metrics.get('win_rate', 0):.2f}% | {metrics.get('profit_factor', 0):.2f} | {metrics.get('total_return_pct', 0):.2f}% |\n")

    print("Report saved to EQUITY_STRESS_TEST_RESULTS.md")

if __name__ == "__main__":
    main()
