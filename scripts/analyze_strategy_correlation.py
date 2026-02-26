import sys
import os
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import importlib.util

# Add openalgo root to path
# Assuming script is run from project root or scripts/ dir
project_root = os.getcwd()
if 'openalgo' not in os.listdir(project_root):
    # Try parent
    project_root = os.path.dirname(project_root)

sys.path.append(os.path.join(project_root))
sys.path.append(os.path.join(project_root, 'openalgo'))
sys.path.append(os.path.join(project_root, 'openalgo', 'strategies', 'scripts'))
sys.path.append(os.path.join(project_root, 'openalgo', 'strategies', 'utils'))

# Mock API Client
class MockClient:
    def __init__(self):
        self.api_key = "MOCK"
        self.host = "http://MOCK"

    def history(self, *args, **kwargs):
        return pd.DataFrame() # return empty df if called, but we pass data directly

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

def generate_mock_data(days=60, interval="15m"):
    """Generate synthetic OHLCV data with some trends."""
    # Handle interval parsing
    if interval.endswith('m') or interval.endswith('min'):
        freq = interval.replace('m', 'min')
    else:
        freq = interval

    dates = pd.date_range(end=datetime.now(), periods=days*25, freq=freq)

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
    # Optimization: iterate last N bars to save time, or skip bars
    start_idx = max(50, len(df) - 500)

    client = MockClient()

    for i in range(start_idx, len(df)):
        window = df.iloc[:i+1]
        try:
            # Check if generate_signal supports full df
            # Try to find a signal generation function
            if hasattr(strategy_module, 'generate_signal'):
                # BaseStrategy style
                res = strategy_module.generate_signal(window, client=client, symbol="MOCK")
            elif hasattr(strategy_module, 'get_signal'):
                 # Try instantiating if class
                 # Need to find class name? Usually derived from BaseStrategy
                 # Simpler: assume module level wrapper exists or try to find class
                 res = 'HOLD'
                 # Find strategy class
                 for attr_name in dir(strategy_module):
                     attr = getattr(strategy_module, attr_name)
                     if isinstance(attr, type) and attr_name.endswith('Strategy'):
                         # Instantiate
                         strat = attr(symbol="MOCK", api_key="MOCK", host="http://MOCK")
                         # Hack: suppress logging
                         import logging
                         strat.logger.setLevel(logging.CRITICAL)
                         res = strat.get_signal(window)
                         break
            else:
                res = 'HOLD'

            # Parse result
            action = 'HOLD'
            if isinstance(res, tuple):
                action = res[0]
            elif isinstance(res, str):
                action = res

            if action == 'BUY':
                signals.append(1)
            elif action == 'SELL':
                signals.append(-1)
            else:
                signals.append(0)

        except Exception as e:
            # print(f"Error in {strategy_module}: {e}")
            signals.append(0)

    return signals

def main():
    print("Loading Active Strategies...")
    strategies = load_active_strategies()
    print(f"Loaded {len(strategies)} strategies.")

    if not strategies:
        print("No strategies found.")
        return

    print("Generating Mock Data...")
    df = generate_mock_data(days=60)
    print(f"Data generated: {len(df)} bars")

    results = {}

    print("Running Strategies...")
    for name, module in strategies.items():
        print(f"  Analysing {name}...")
        signals = get_strategy_signals(module, df)
        # Only keep if signals vary (not all 0)
        if any(signals):
            results[name] = signals
        else:
            print(f"    No signals generated for {name} (or all HOLD)")

    if not results:
        print("No signals generated from any strategy.")
        return

    # Pad to same length if needed (should be same)
    min_len = min(len(s) for s in results.values())
    data = {k: v[:min_len] for k, v in results.items()}

    df_signals = pd.DataFrame(data)

    # Correlation
    print("\nCorrelation Matrix:")
    corr_matrix = df_signals.corr()
    print(corr_matrix)

    # Output to File
    with open("CORRELATION_ANALYSIS.md", "w") as f:
        f.write("# Strategy Correlation Analysis\n\n")
        f.write(f"**Date**: {datetime.now().strftime('%Y-%m-%d')}\n")
        f.write(f"**Strategies Analyzed**: {len(results)}\n\n")

        f.write("## High Correlation Pairs (>0.7)\n")
        found = False

        # Use tabulate if available, else markdown manually
        rows = []

        for i in range(len(corr_matrix.columns)):
            for j in range(i+1, len(corr_matrix.columns)):
                val = corr_matrix.iloc[i, j]
                if abs(val) > 0.7:
                    rows.append([corr_matrix.columns[i], corr_matrix.columns[j], f"{val:.2f}"])
                    found = True

        if rows:
            f.write("| Strategy A | Strategy B | Correlation |\n")
            f.write("|------------|------------|-------------|\n")
            for r in rows:
                f.write(f"| {r[0]} | {r[1]} | {r[2]} |\n")
        else:
            f.write("None found.\n")

        f.write("\n## Full Matrix\n")
        f.write("```\n")
        f.write(corr_matrix.to_string())
        f.write("\n```\n")

    print("\nHigh Correlation Pairs (>0.7):")
    if found:
        for r in rows:
            print(f"  {r[0]} vs {r[1]}: {r[2]}")
    else:
        print("  None found.")

    print("\nResults saved to CORRELATION_ANALYSIS.md")

if __name__ == "__main__":
    main()
