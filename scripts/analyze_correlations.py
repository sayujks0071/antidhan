import os
import glob
import sys
import pandas as pd
import numpy as np
import importlib.util

# Add project root to path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "openalgo"))
# Add strategies scripts dir to path for strategy_preamble
sys.path.append(os.path.join(os.getcwd(), "openalgo/strategies/scripts"))
# Add strategies utils dir to path just in case
sys.path.append(os.path.join(os.getcwd(), "openalgo/strategies/utils"))

try:
    from base_strategy import BaseStrategy
except ImportError:
    from openalgo.strategies.utils.base_strategy import BaseStrategy

STRATEGIES_DIR = "openalgo/strategies/scripts"
OUTPUT_FILE = "CORRELATION_ANALYSIS.md"

def load_strategy_class(filepath):
    """Load strategy class from file dynamically."""
    try:
        spec = importlib.util.spec_from_file_location("strategy_module", filepath)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Find class inheriting from BaseStrategy
        for name, obj in module.__dict__.items():
            if isinstance(obj, type) and issubclass(obj, BaseStrategy) and obj is not BaseStrategy:
                return obj
    except Exception as e:
        print(f"Failed to load {filepath}: {e}")
    return None

def generate_mock_data(symbol, days=30):
    """Generate mock 5m candle data."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    dates = pd.date_range(start=start_date, end=end_date, freq="5min")

    # Random walk
    base_price = 24000 if "NIFTY" in symbol else (6000 if "CRUDE" in symbol else 1000)
    prices = [base_price]
    for _ in range(len(dates)-1):
        change = prices[-1] * np.random.normal(0, 0.001)
        prices.append(prices[-1] + change)

    df = pd.DataFrame({
        "datetime": dates,
        "open": prices,
        "high": [p * 1.001 for p in prices],
        "low": [p * 0.999 for p in prices],
        "close": prices,
        "volume": np.random.randint(100, 10000, size=len(dates))
    })
    df.set_index("datetime", inplace=True)
    return df

from datetime import datetime, timedelta

def main():
    print("Analyzing strategy correlations...")

    strategy_files = glob.glob(os.path.join(STRATEGIES_DIR, "*.py"))
    strategies = {}

    # Load strategies
    for filepath in strategy_files:
        if "__init__" in filepath or "preamble" in filepath: continue

        cls = load_strategy_class(filepath)
        if cls:
            strategies[cls.__name__] = cls
            print(f"Loaded {cls.__name__}")

    if not strategies:
        print("No strategies found.")
        return

    # Generate signals
    # Common index (using NIFTY mock data timestamps)
    common_df = generate_mock_data("NIFTY")

    # We will store signals in a dict then DataFrame
    signals_data = {}

    # Sample points
    sample_indices = np.linspace(50, len(common_df)-1, 100, dtype=int)

    # Mock Client to prevent API calls
    class MockClient:
        def __init__(self): pass
        def history(self, *args, **kwargs): return pd.DataFrame()
        def get_quote(self, *args, **kwargs): return {"ltp": 24000.0}

    for name, cls in strategies.items():
        print(f"Generating signals for {name}...")
        try:
            strategy_signals = []

            # Instantiate once with mock client
            strat_instance = cls(symbol="BACKTEST", api_key="test", ignore_time=True, client=MockClient())
            # Suppress logging
            strat_instance.logger.setLevel(logging.ERROR)

            for idx in sample_indices:
                slice_df = common_df.iloc[:idx+1].copy()

                # If strategy relies on `calculate_indicators` in `default_cycle`, we must call it.
                if hasattr(strat_instance, "calculate_indicators"):
                    slice_df = strat_instance.calculate_indicators(slice_df)

                try:
                    # Prefer get_signal for backtesting (pure logic on df)
                    # generate_signal might fetch history internally (ignoring df)
                    if hasattr(strat_instance, "get_signal"):
                         sig = strat_instance.get_signal(slice_df)
                    elif hasattr(strat_instance, "generate_signal"):
                         # Risky fallback
                         sig = strat_instance.generate_signal(slice_df)
                    else:
                         sig = "HOLD"

                    # Normalize signal
                    if isinstance(sig, tuple): sig = sig[0]

                    val = 0
                    if sig == "BUY": val = 1
                    elif sig == "SELL": val = -1
                    strategy_signals.append(val)
                except Exception as e:
                    # print(f"Error signal {name}: {e}")
                    strategy_signals.append(0)

            signals_data[name] = strategy_signals

        except Exception as e:
            print(f"Skipping {name}: {e}")

    # Create DataFrame
    if not signals_data:
        print("No signals generated.")
        return

    signals_df = pd.DataFrame(signals_data)

    # Calculate Correlation
    if signals_df.empty:
        print("No signals generated.")
        return

    correlation_matrix = signals_df.corr()

    # Report
    with open(OUTPUT_FILE, "w") as f:
        f.write("# Cross-Strategy Correlation Analysis\n\n")
        f.write("Method: Ran strategies on 100 sampled points of common market data (Random Walk) to identify algorithmic similarity.\n\n")

        f.write("## Correlation Matrix\n")
        f.write(correlation_matrix.to_markdown())
        f.write("\n\n")

        f.write("## High Correlation Pairs (>70%)\n")
        pairs = []
        cols = correlation_matrix.columns
        for i in range(len(cols)):
            for j in range(i+1, len(cols)):
                corr = correlation_matrix.iloc[i, j]
                if abs(corr) > 0.7:
                    f.write(f"- **{cols[i]}** vs **{cols[j]}**: {corr:.2f}\n")
                    pairs.append((cols[i], cols[j], corr))

        if not pairs:
            f.write("None found. Strategies appear distinct.\n")
        else:
            f.write("\n### Recommendations\n")
            for s1, s2, corr in pairs:
                f.write(f"- Consider merging **{s1}** and **{s2}** (Correlation: {corr:.2f}). Keep the one with better Calmar Ratio.\n")

    print(f"Correlation analysis saved to {OUTPUT_FILE}")

import logging
if __name__ == "__main__":
    main()
