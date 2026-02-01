#!/usr/bin/env python3
import os
import sys
import json
import logging
import random
import argparse
import importlib
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Add repo root to path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.append(repo_root)

from openalgo.strategies.utils.simple_backtest_engine import SimpleBacktestEngine
from openalgo.strategies.utils.symbol_resolver import SymbolResolver
from openalgo.strategies.utils.trading_utils import APIClient
from openalgo.utils.data_validator import DataValidator

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DailyBacktest")

CONFIG_FILE = os.path.join(repo_root, 'openalgo/strategies/active_strategies.json')
DATA_DIR = os.path.join(repo_root, 'openalgo/data')

class BenchmarkManager:
    """Manages fetching and calculating benchmark returns (NIFTY 50)."""
    def __init__(self, api_client):
        self.api_client = api_client
        self.benchmark_data = None
        self.benchmark_symbol = "NIFTY 50"

    def fetch_data(self, days=30):
        if not self.api_client:
            return None

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        try:
            df = self.api_client.history(
                symbol=self.benchmark_symbol,
                exchange="NSE_INDEX",
                interval="1d", # Daily returns are sufficient for benchmark
                start_date=start_date.strftime("%Y-%m-%d %H:%M:%S"),
                end_date=end_date.strftime("%Y-%m-%d %H:%M:%S")
            )
            if not df.empty:
                self.benchmark_data = df
                logger.info(f"Fetched Benchmark Data for {self.benchmark_symbol}")
            else:
                logger.warning("Benchmark data fetch failed/empty.")
        except Exception as e:
            logger.warning(f"Could not fetch benchmark data: {e}")

    def calculate_return(self, start_date, end_date):
        if self.benchmark_data is None or self.benchmark_data.empty:
            return 0.0

        # Filter for range
        mask = (self.benchmark_data.index >= start_date) & (self.benchmark_data.index <= end_date)
        period_data = self.benchmark_data.loc[mask]

        if period_data.empty:
            return 0.0

        start_price = period_data.iloc[0]['close']
        end_price = period_data.iloc[-1]['close']

        return ((end_price - start_price) / start_price) * 100

class DailyBacktester:
    def __init__(self, source='mock', days=90, api_key=None, host="http://127.0.0.1:5001", optimize=False):
        self.resolver = SymbolResolver()
        self.results = []
        self.source = source
        self.days = days
        self.optimize = optimize
        self.api_key = api_key or os.getenv('OPENALGO_APIKEY', "dummy_key")
        self.host = host
        self.api_client = None

        if self.source == 'api':
            self.api_client = APIClient(self.api_key, self.host)
            self.benchmark_manager = BenchmarkManager(self.api_client)
        else:
            self.benchmark_manager = None

    def load_configs(self):
        if not os.path.exists(CONFIG_FILE):
            logger.error(f"Config file not found: {CONFIG_FILE}")
            return {}
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)

    def load_strategy_module(self, strategy_name):
        """Dynamically import strategy module."""
        try:
            # Try specific paths
            paths = [
                f"openalgo.strategies.scripts.{strategy_name}",
                f"vendor.openalgo.strategies.scripts.{strategy_name}"
            ]
            for path in paths:
                try:
                    module = importlib.import_module(path)
                    return module
                except ImportError:
                    continue
            logger.error(f"Could not import strategy module: {strategy_name}")
            return None
        except Exception as e:
            logger.error(f"Error loading strategy {strategy_name}: {e}")
            return None

    def generate_mock_data(self, symbol, days=30):
        # Generate slightly realistic data with trends
        dates = pd.date_range(end=datetime.now(), periods=days*75, freq='15min') # Reduced freq for Mock
        price = 10000
        opens = []
        for _ in range(len(dates)):
            change = random.normalvariate(0, 5)
            price += change
            opens.append(price)

        df = pd.DataFrame({
            'datetime': dates,
            'open': opens,
            'volume': [random.randint(100, 1000) for _ in range(len(dates))]
        })
        df['close'] = df['open'] + [random.normalvariate(0, 2) for _ in range(len(dates))]
        df['high'] = df[['open', 'close']].max(axis=1) + 2
        df['low'] = df[['open', 'close']].min(axis=1) - 2

        # Add timestamp column for some strategies that check it
        df['timestamp'] = df['datetime']
        df.set_index('datetime', inplace=True)
        return df

    def run_strategy_simulation(self, name, config, symbol, override_params=None):
        logger.info(f"Backtesting {name} ({symbol})...")

        # Initialize Engine
        engine = SimpleBacktestEngine(initial_capital=100000, api_key=self.api_key, host=self.host)

        strategy_module_name = config.get('strategy')
        strategy_module = self.load_strategy_module(strategy_module_name)

        if not strategy_module:
            return {'strategy': name, 'symbol': symbol, 'error': f'Module {strategy_module_name} not found'}

        # Prepare Params (Wrap module generate_signal if needed)
        # We need a wrapper that passes params to generate_signal
        original_gen = strategy_module.generate_signal

        params = config.get('params', {}).copy()
        if override_params:
            params.update(override_params)

        # Create a partial/wrapper for the strategy module
        # This hack allows SimpleBacktestEngine to call module.generate_signal(df, client, symbol)
        # while we inject 'params'
        class ModuleWrapper:
            def generate_signal(self, df, client=None, symbol=None):
                # Check signature of original function to see if it accepts params
                # Most don't, but our new orb_strategy wrapper does.
                # If not, we rely on the strategy class init inside the wrapper using default params
                # OR we need to update the wrapper in the file.
                # For now, we assume the module-level generate_signal might accept params OR
                # we need to pass them via another way.
                # Since we can't easily modify the installed module code, we try to pass params if supported.
                try:
                    return original_gen(df, client=client, symbol=symbol, params=params)
                except TypeError:
                    # Fallback if params arg not supported
                    return original_gen(df, client=client, symbol=symbol)

            # Proxy other attributes
            def __getattr__(self, name):
                return getattr(strategy_module, name)

        wrapped_module = ModuleWrapper()

        # Proxy check_exit if exists
        if hasattr(strategy_module, 'check_exit'):
             wrapped_module.check_exit = strategy_module.check_exit

        # Fetch Data (Managed by Engine usually, but we want to control source)
        start_date = (datetime.now() - timedelta(days=self.days)).strftime("%Y-%m-%d")
        end_date = datetime.now().strftime("%Y-%m-%d")

        if self.source == 'mock':
            # Mock Data Injection
            # SimpleBacktestEngine loads data via APIClient.history
            # We can monkey patch client.history for this engine instance
            mock_df = self.generate_mock_data(symbol, self.days)
            engine.client.history = lambda **kwargs: mock_df
            validation_valid = True
            validation_issues = []
        else:
             # Real API usage handled by Engine
             validation_valid = True # We assume Engine handles it or we validate separately?
             validation_issues = []

        try:
            res = engine.run_backtest(
                strategy_module=wrapped_module,
                symbol=symbol,
                exchange=config.get('exchange', 'NSE'),
                start_date=start_date,
                end_date=end_date,
                interval="15m" # Default backtest interval
            )
        except Exception as e:
            logger.error(f"Backtest Failed: {e}", exc_info=True)
            return {'strategy': name, 'symbol': symbol, 'error': str(e)}

        if 'error' in res:
             return {'strategy': name, 'symbol': symbol, 'error': res['error']}

        metrics = res.get('metrics', {})
        metrics['strategy'] = name
        metrics['symbol'] = symbol
        metrics['params'] = params
        metrics['data_source'] = self.source

        # Benchmark Comparison
        if self.benchmark_manager and self.source == 'api':
             # Approximate start/end from actual data
             if res['closed_trades']:
                  first_trade = res['closed_trades'][0]['entry_time'] # datetime
                  last_trade = res['closed_trades'][-1]['exit_time']
                  # Use string dates passed to backtest for simpler benchmark calc
                  b_return = self.benchmark_manager.calculate_return(start_date, end_date)
                  metrics['benchmark_return_pct'] = b_return
                  metrics['alpha'] = metrics['total_return_pct'] - b_return
             else:
                  metrics['benchmark_return_pct'] = 0.0
                  metrics['alpha'] = 0.0
        else:
             metrics['benchmark_return_pct'] = 0.0
             metrics['alpha'] = 0.0

        return metrics

    def validate_risk(self, metrics):
        """Validate if strategy meets risk criteria."""
        failures = []
        if metrics.get('max_drawdown_pct', 0) > 20.0:
            failures.append("Max DD > 20%")
        if metrics.get('sharpe_ratio', 0) < 0.5:
             failures.append("Sharpe < 0.5")
        if metrics.get('win_rate', 0) < 30.0:
             failures.append("Win Rate < 30%")

        metrics['risk_failures'] = failures
        metrics['risk_passed'] = len(failures) == 0
        return metrics

    def optimize_strategy(self, name, config, symbol):
        logger.info(f"Optimizing {name}...")

        strategy_module = self.load_strategy_module(config.get('strategy'))
        if not strategy_module or not hasattr(strategy_module, 'TUNABLE_PARAMS'):
             logger.info(f"No tunable params for {name}")
             return

        import itertools
        tunable = strategy_module.TUNABLE_PARAMS
        keys = list(tunable.keys())
        values = list(tunable.values())
        combinations = list(itertools.product(*values))

        best_sharpe = -999
        best_params = None

        for combo in combinations:
             params = dict(zip(keys, combo))
             # Merge with base params logic handled in run_strategy_simulation via override_params

             metrics = self.run_strategy_simulation(name, config, symbol, override_params=params)
             if metrics.get('sharpe_ratio', -999) > best_sharpe:
                  best_sharpe = metrics['sharpe_ratio']
                  best_params = params

        logger.info(f"🏆 Best Params for {name}: {best_params} (Sharpe: {best_sharpe:.2f})")
        return best_params

    def run(self):
        configs = self.load_configs()

        if self.source == 'api' and self.benchmark_manager:
            self.benchmark_manager.fetch_data(self.days)

        print(f"\n🚀 STARTING DAILY BACKTESTS (Source: {self.source}, Days: {self.days})")

        for name, config in configs.items():
            resolved = self.resolver.resolve(config)
            symbol = resolved if isinstance(resolved, str) else resolved.get('sample_symbol', 'UNKNOWN')

            metrics = self.run_strategy_simulation(name, config, symbol)
            if 'error' in metrics:
                logger.error(f"Error in {name}: {metrics['error']}")
                continue

            metrics = self.validate_risk(metrics)
            self.results.append(metrics)

        self.generate_report()
        self.generate_leaderboard()

    def generate_report(self):
        df = pd.DataFrame(self.results)
        if df.empty:
             print("No results.")
             return

        cols = ['strategy', 'symbol', 'total_return_pct', 'benchmark_return_pct', 'alpha', 'sharpe_ratio', 'max_drawdown_pct', 'risk_passed']

        # Clean formatting
        print("\n📊 BACKTEST VALIDATION REPORT")
        print(df[cols].sort_values('sharpe_ratio', ascending=False).to_markdown(index=False, floatfmt=".2f"))

        # Detail Failures
        failures = df[~df['risk_passed']]
        if not failures.empty:
             print("\n⚠️ RISK VALIDATION FAILURES:")
             for _, row in failures.iterrows():
                  print(f"- {row['strategy']}: {', '.join(row['risk_failures'])}")

    def generate_leaderboard(self):
        output_file = os.path.join(repo_root, 'leaderboard.json')
        # Serialize params/failures (ensure list/dict)
        with open(output_file, 'w') as f:
            # Convert failures list to string for easier JSON reading if needed, or keep structure
            json.dump(self.results, f, indent=4, default=str)
        logger.info(f"Leaderboard saved to {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run daily backtests")
    parser.add_argument("--source", choices=['mock', 'api'], default='mock', help="Data source: 'mock' or 'api'")
    parser.add_argument("--days", type=int, default=90, help="Number of days to backtest (Default: 90)")
    parser.add_argument("--api-key", type=str, default=None, help="API Key for real data")
    parser.add_argument("--host", type=str, default="http://127.0.0.1:5001", help="Broker API Host")
    parser.add_argument("--optimize", action="store_true", help="Enable parameter optimization")

    args = parser.parse_args()

    runner = DailyBacktester(source=args.source, days=args.days, api_key=args.api_key, host=args.host, optimize=args.optimize)
    runner.run()
