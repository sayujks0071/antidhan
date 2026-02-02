#!/usr/bin/env python3
"""
Performance Analysis Script
---------------------------
Runs backtests on all strategies in strategies/scripts/ using OpenAlgoAPIMock
and available historical data (Aug 2025).
"""
import os
import sys
import json
import importlib.util
import logging
from datetime import datetime
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Analysis")

# Add paths
current_dir = Path(__file__).resolve().parent
openalgo_root = current_dir.parent / "openalgo"
strategies_dir = openalgo_root / "strategies"
scripts_dir = strategies_dir / "scripts"
utils_dir = strategies_dir / "utils"

sys.path.insert(0, str(openalgo_root))
# Do not add strategies_dir to path to avoid 'utils' name conflict
# sys.path.insert(0, str(strategies_dir))
sys.path.insert(0, str(utils_dir))

# Set dummy env vars for AITRAPP
os.environ.setdefault("KITE_API_KEY", "dummy")
os.environ.setdefault("KITE_API_SECRET", "dummy")
os.environ.setdefault("KITE_ACCESS_TOKEN", "dummy")
os.environ.setdefault("KITE_USER_ID", "dummy")
os.environ.setdefault("DATABASE_URL", "sqlite:///")
os.environ.setdefault("REDIS_URL", "redis://localhost")
os.environ.setdefault("API_SECRET_KEY", "dummy")

# Imports
try:
    # utils_dir is in sys.path, so import directly
    from simple_backtest_engine import SimpleBacktestEngine
    from openalgo_mock import set_current_timestamp, OpenAlgoAPIMock
    from base_strategy import BaseStrategy
except ImportError as e:
    logger.error(f"Import Error: {e}")
    # Try alternate path structure if running from root
    sys.path.insert(0, str(current_dir.parent))
    try:
        from openalgo.strategies.utils.simple_backtest_engine import SimpleBacktestEngine
        from openalgo.strategies.utils.openalgo_mock import set_current_timestamp, OpenAlgoAPIMock
        from openalgo.strategies.utils.base_strategy import BaseStrategy
    except ImportError as e2:
        logger.error(f"Fatal Import Error: {e2}")
        sys.exit(1)

def load_strategy_class(filepath):
    """Load strategy class from file, or return module if it has generate_signal"""
    try:
        spec = importlib.util.spec_from_file_location("strategy_module", filepath)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Find class inheriting from BaseStrategy
        for name, obj in module.__dict__.items():
            if isinstance(obj, type) and issubclass(obj, BaseStrategy) and obj is not BaseStrategy:
                return obj

        # If no class, check for generate_signal function
        if hasattr(module, 'generate_signal'):
            return module

        return None
    except Exception as e:
        logger.error(f"Failed to load {filepath}: {e}")
        return None

def main():
    results = {}

    # Date range for backtest (based on available data)
    start_date = "2025-08-12"
    end_date = "2025-08-19"

    # List strategy files
    strategy_files = list(scripts_dir.glob("*.py"))

    for strategy_file in strategy_files:
        if strategy_file.name == "__init__.py":
            continue

        logger.info(f"Analyzing {strategy_file.name}...")

        StrategyClass = load_strategy_class(strategy_file)
        if not StrategyClass:
            logger.warning(f"No strategy class found in {strategy_file.name}")
            continue

        strategy_name = getattr(StrategyClass, '__name__', strategy_file.name)

        try:
            # Instantiate engine
            engine = SimpleBacktestEngine(initial_capital=100000.0, api_key="TEST", host="http://mock")

            class MockClientWrapper:
                def __init__(self):
                    self.host = "http://mock"
                    self.api_key = "TEST"

                def history(self, **kwargs):
                    if 'end_date' in kwargs:
                        try:
                            ts = datetime.strptime(kwargs['end_date'], "%Y-%m-%d")
                            set_current_timestamp(ts)
                        except:
                            pass

                    m = OpenAlgoAPIMock(datetime.now())
                    payload = kwargs
                    response = m.post_json("history", payload)

                    if response.get("status") == "success":
                        import pandas as pd
                        df = pd.DataFrame(response["data"])
                        if not df.empty and "time" in df.columns:
                            df["datetime"] = pd.to_datetime(df["time"])
                            df = df.set_index("datetime")
                            for col in ["open", "high", "low", "close", "volume"]:
                                if col not in df.columns: df[col] = 0.0
                        return df
                    return None

            engine.client = MockClientWrapper()

            # Instantiate strategy
            if isinstance(StrategyClass, type):
                strategy = StrategyClass(
                    symbol="BANKNIFTY",
                    quantity=25,
                    api_key="TEST",
                    client=engine.client
                )
            else:
                # It's a module
                strategy = StrategyClass

            # Run backtest with 1d interval due to EOD data
            backtest_result = engine.run_backtest(
                strategy_module=strategy,
                symbol="BANKNIFTY",
                exchange="NSE",
                start_date=start_date,
                end_date=end_date,
                interval="1d"
            )

            metrics = backtest_result['metrics']
            results[strategy_name] = {
                "file": strategy_file.name,
                "pnl": metrics.get("total_return_pct", 0.0) * 100000.0 / 100.0, # Convert % back to abs PnL approx
                "profit_factor": metrics.get("profit_factor", 0.0),
                "trades": metrics.get("total_trades", 0),
                "win_rate": metrics.get("win_rate", 0.0)
            }

            logger.info(f"{strategy_name}: PnL={results[strategy_name]['pnl']:.2f}, PF={results[strategy_name]['profit_factor']:.2f}")

        except Exception as e:
            logger.error(f"Error running {strategy_name}: {e}", exc_info=True)
            # Default failure result
            results[strategy_name] = {
                "file": strategy_file.name,
                "pnl": -9999.0,
                "profit_factor": 0.0,
                "trades": 0,
                "error": str(e)
            }

    # Save results
    with open("analysis_results.json", "w") as f:
        json.dump(results, f, indent=4)

if __name__ == "__main__":
    main()
