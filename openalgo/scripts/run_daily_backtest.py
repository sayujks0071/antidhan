#!/usr/bin/env python3
import os
import sys
import json
import logging
import random
import argparse
import pandas as pd
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

class ORBStrategy:
    """
    Simple ORB Strategy implementation for backtesting.
    """
    def __init__(self, symbol, quantity, range_mins=15, api_key=None):
        self.symbol = symbol
        self.quantity = quantity
        self.range_mins = range_mins

    def calculate_signals(self, df):
        """
        Backtest logic: Process a DataFrame and return signals.
        """
        signals = []
        if df.empty:
            return signals

        # Ensure datetime
        if 'datetime' not in df.columns:
            df['datetime'] = df.index

        # Work on copy
        df = df.copy()
        df['date'] = df['datetime'].dt.date

        # Process each day independently
        for date, day_df in df.groupby('date'):
            if len(day_df) < self.range_mins:
                continue

            # Calculate ORB for this day
            orb_df = day_df.iloc[:self.range_mins]
            orb_high = orb_df['high'].max()
            orb_low = orb_df['low'].min()
            orb_vol_avg = orb_df['volume'].mean()

            position = 0

            # Trading Session (after ORB)
            # Use iloc relative to day_df
            trading_df = day_df.iloc[self.range_mins:]

            for i in range(len(trading_df)):
                candle = trading_df.iloc[i]
                ts = candle['datetime']

                # Entry Logic
                if position == 0:
                    if candle['close'] > orb_high and candle['volume'] > orb_vol_avg:
                        signals.append({'time': ts, 'side': 'BUY', 'price': candle['close']})
                        position = 1
                    elif candle['close'] < orb_low and candle['volume'] > orb_vol_avg:
                        signals.append({'time': ts, 'side': 'SELL', 'price': candle['close']})
                        position = -1

                # Exit Logic (Simple EOD)
                if i == len(trading_df) - 1 and position != 0:
                     side = 'SELL' if position == 1 else 'BUY'
                     signals.append({'time': ts, 'side': side, 'price': candle['close'], 'reason': 'EOD'})
                     position = 0

        return signals

class DailyBacktester:
    def __init__(self, source='mock', days=30, api_key=None, host="http://127.0.0.1:5001"):
        self.resolver = SymbolResolver()
        self.results = []
        self.source = source
        self.days = days
        self.api_key = api_key or "dummy_key"
        self.host = host
        self.api_client = None

        if self.source == 'api':
            self.api_client = APIClient(self.api_key, self.host)

    def load_configs(self):
        if not os.path.exists(CONFIG_FILE):
            logger.error(f"Config file not found: {CONFIG_FILE}")
            return {}
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)

    def generate_mock_data(self, symbol, days=30):
        # Generate slightly realistic data with trends
        dates = pd.date_range(end=datetime.now(), periods=days*75, freq='5min')
        price = 100
        opens = []
        for _ in range(len(dates)):
            change = random.normalvariate(0, 0.5)
            price += change
            opens.append(price)

        df = pd.DataFrame({
            'datetime': dates,
            'open': opens,
            'volume': [random.randint(100, 1000) for _ in range(len(dates))]
        })
        df['close'] = df['open'] + [random.normalvariate(0, 0.2) for _ in range(len(dates))]
        df['high'] = df[['open', 'close']].max(axis=1) + 0.2
        df['low'] = df[['open', 'close']].min(axis=1) - 0.2
        return df

    def fetch_real_data(self, symbol, days=30):
        """Fetch real data from API and validate it."""
        if not self.api_client:
            logger.error("API Client not initialized.")
            return pd.DataFrame()

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        logger.info(f"Fetching data for {symbol} from {start_date.date()} to {end_date.date()}")

        df = self.api_client.history(
            symbol=symbol,
            exchange="NSE", # Defaulting to NSE, logic can be enhanced
            interval="5m",
            start_date=start_date.strftime("%Y-%m-%d %H:%M:%S"),
            end_date=end_date.strftime("%Y-%m-%d %H:%M:%S")
        )

        if df.empty:
            logger.warning(f"No data returned for {symbol}")
            return df

        # Validate Data
        validation = DataValidator.validate_ohlcv(df, symbol=symbol, interval_minutes=5)
        if not validation['is_valid']:
            logger.warning(f"Data Validation Issues for {symbol}: {validation['issues']}")
        else:
            logger.info(f"Data Validation Passed for {symbol}")

        # Store validation stats for report
        self.current_validation_stats = validation

        return df

    def run_strategy_simulation(self, name, config, symbol, override_params=None):
        logger.info(f"Backtesting {name} ({symbol})...")
        engine = SimpleBacktestEngine(initial_capital=100000)

        if self.source == 'api':
            df = self.fetch_real_data(symbol, self.days)
            if df.empty:
                logger.error(f"Skipping {name}: No data.")
                return {'strategy': name, 'symbol': symbol, 'error': 'No Data'}
        else:
            df = self.generate_mock_data(symbol, self.days)
            self.current_validation_stats = {'is_valid': True, 'note': 'Mock Data'}

        signals = []

        params = config.get('params', {}).copy()
        if override_params:
            params.update(override_params)

        strategy_type = config.get('strategy')

        if strategy_type == 'orb_strategy':
            try:
                # Pass dummy API key for backtesting
                strat = ORBStrategy(symbol, params.get('quantity', 10),
                                  range_mins=params.get('minutes', 15),
                                  api_key='backtest_dummy_key')
                signals = strat.calculate_signals(df)
            except Exception as e:
                logger.error(f"Failed to run ORB logic: {e}")
                signals = []
        else:
            signals = self._simulate_fallback_signals(df, config)

        self._process_signals(engine, signals, params.get('quantity', 10))

        metrics = engine.calculate_metrics()
        metrics['strategy'] = name
        metrics['symbol'] = symbol
        metrics['params'] = params
        metrics['data_source'] = self.source
        metrics['data_valid'] = self.current_validation_stats.get('is_valid', False)
        metrics['data_issues'] = len(self.current_validation_stats.get('issues', []))
        return metrics

    def _simulate_fallback_signals(self, df, config):
        signals = []
        # Random logic for fallback
        for i in range(10, len(df), 50): # One trade every 50 candles
             row = df.iloc[i]
             ts = row['datetime']
             signals.append({'time': ts, 'side': 'BUY', 'price': row['close']})
             # Exit later
             if i+20 < len(df):
                 exit_row = df.iloc[i+20]
                 signals.append({'time': exit_row['datetime'], 'side': 'SELL', 'price': exit_row['close']})
        return signals

    def _process_signals(self, engine, signals, quantity):
        position = 0
        entry_price = 0.0

        for sig in signals:
            price = float(sig['price'])
            side = sig['side']

            if side == 'BUY':
                if position == 0:
                    position = quantity
                    entry_price = price
                elif position < 0:
                    # Cover Short
                    pnl = (entry_price - price) * quantity
                    self._add_trade(engine, pnl, entry_price, quantity)
                    position = 0
            elif side == 'SELL':
                if position == 0:
                    position = -quantity
                    entry_price = price
                elif position > 0:
                    # Sell Long
                    pnl = (price - entry_price) * quantity
                    self._add_trade(engine, pnl, entry_price, quantity)
                    position = 0

    def _add_trade(self, engine, pnl, entry_price, qty):
        class MockTrade:
            def __init__(self, pnl, pnl_pct):
                self.pnl = pnl
                self.pnl_pct = pnl_pct
                self.entry_time = datetime.now()
                self.exit_time = datetime.now()

        pnl_pct = (pnl / (entry_price * qty)) * 100
        t = MockTrade(pnl, pnl_pct)
        engine.closed_trades.append(t)
        engine.current_capital += pnl
        engine.equity_curve.append((t.exit_time, engine.current_capital))

    def optimize_strategy(self, name, config, symbol):
        logger.info(f"optimizing {name}...")
        best_sharpe = -999
        best_params = None

        # Simple Grid Search for ORB minutes
        if config.get('strategy') == 'orb_strategy':
            current_mins = config.get('params', {}).get('minutes', 15)
            variations = [current_mins - 5, current_mins, current_mins + 5, current_mins + 15]
            variations = [v for v in variations if v > 0]

            for mins in variations:
                metrics = self.run_strategy_simulation(name, config, symbol, override_params={'minutes': mins})
                sharpe = metrics.get('sharpe_ratio', 0)
                logger.info(f"Params: minutes={mins} -> Sharpe: {sharpe:.2f}")

                if sharpe > best_sharpe:
                    best_sharpe = sharpe
                    best_params = metrics['params']

            logger.info(f"Best Params for {name}: {best_params} (Sharpe: {best_sharpe:.2f})")
            return best_params

    def run(self):
        configs = self.load_configs()

        print(f"\n🚀 STARTING DAILY BACKTESTS (Source: {self.source})")

        for name, config in configs.items():
            resolved = self.resolver.resolve(config)
            symbol = resolved if isinstance(resolved, str) else resolved.get('sample_symbol', 'UNKNOWN')

            metrics = self.run_strategy_simulation(name, config, symbol)
            if 'error' in metrics:
                continue

            self.results.append(metrics)

            # Optimization Loop for ORB (Only on mock or valid data)
            if config.get('strategy') == 'orb_strategy' and self.source == 'mock':
                self.optimize_strategy(name, config, symbol)

        self.generate_report()
        self.generate_leaderboard()

    def generate_report(self):
        df = pd.DataFrame(self.results)
        if df.empty:
             print("No results.")
             return

        cols = ['strategy', 'symbol', 'total_return_pct', 'win_rate', 'profit_factor', 'sharpe_ratio', 'max_drawdown_pct', 'data_valid']
        print("\n📊 BACKTEST LEADERBOARD")
        print(df[cols].sort_values('sharpe_ratio', ascending=False).to_markdown(index=False))

    def generate_leaderboard(self):
        output_file = os.path.join(repo_root, 'leaderboard.json')
        # Convert any non-serializable objects if needed (handled by basic types here)
        with open(output_file, 'w') as f:
            json.dump(self.results, f, indent=4)
        logger.info(f"Leaderboard saved to {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run daily backtests")
    parser.add_argument("--source", choices=['mock', 'api'], default='mock', help="Data source: 'mock' or 'api'")
    parser.add_argument("--days", type=int, default=30, help="Number of days to backtest")
    parser.add_argument("--api-key", type=str, default=None, help="API Key for real data")
    parser.add_argument("--host", type=str, default="http://127.0.0.1:5001", help="Broker API Host")

    args = parser.parse_args()

    runner = DailyBacktester(source=args.source, days=args.days, api_key=args.api_key, host=args.host)
    runner.run()
