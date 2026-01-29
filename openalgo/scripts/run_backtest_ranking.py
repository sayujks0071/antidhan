#!/usr/bin/env python3
"""
Backtest Ranking Script
Run backtests for all strategies using their adapters and rank them.
"""
import os
import sys
import importlib
import inspect
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta, time
from collections import defaultdict
import json

# Setup paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
OPENALGO_ROOT = os.path.join(PROJECT_ROOT, 'openalgo')
STRATEGIES_DIR = os.path.join(OPENALGO_ROOT, 'strategies')
ADAPTERS_DIR = os.path.join(STRATEGIES_DIR, 'adapters')
UTILS_DIR = os.path.join(STRATEGIES_DIR, 'utils')

sys.path.insert(0, UTILS_DIR)
sys.path.insert(0, OPENALGO_ROOT)
sys.path.insert(0, PROJECT_ROOT)

# Set Mock Env Vars for AITRAPP Config Validation
os.environ.setdefault('KITE_ACCESS_TOKEN', 'mock_token')
os.environ.setdefault('KITE_USER_ID', 'mock_user')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('REDIS_URL', 'redis://localhost:6379/0')
os.environ.setdefault('API_SECRET_KEY', 'mock_secret')

# Import Utils
try:
    from openalgo_mock import set_current_timestamp, get_mock
    from aitrapp_integration import StrategyContext, SignalSide, Instrument, InstrumentType
    from strategy_adapter import StrategyAdapter
except ImportError as e:
    print(f"Error importing backtest utils: {e}")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format='[BACKTEST] %(message)s')
logger = logging.getLogger(__name__)

class SimpleBacktestEngine:
    def __init__(self, start_date, end_date):
        self.start_date = start_date
        self.end_date = end_date
        self.results = {}

    def run(self, adapters):
        """Run backtest for list of adapters"""
        dates = pd.date_range(self.start_date, self.end_date, freq='B') # Business days

        for adapter_cls in adapters:
            try:
                adapter = adapter_cls()
                strategy_name = adapter.name
                logger.info(f"Testing {strategy_name}...")

                trades = []
                equity = 100000.0
                initial_equity = equity

                for date in dates:
                    # Run for market hours 9:15 to 15:30
                    current_time = datetime.combine(date, time(9, 15))
                    end_time = datetime.combine(date, time(15, 30))

                    while current_time <= end_time:
                        set_current_timestamp(current_time)

                        # Create dummy instrument for context
                        dummy_instrument = Instrument(
                            token=0,
                            symbol="NIFTY",
                            tradingsymbol="NIFTY",
                            exchange="NSE",
                            instrument_type=InstrumentType.EQ,
                            strike=0.0,
                            lot_size=1,
                            tick_size=0.05
                        )

                        context = StrategyContext(
                            timestamp=current_time,
                            instrument=dummy_instrument,
                            net_liquid=equity
                        )

                        try:
                            signals = adapter._extract_signals(context)
                            for signal in signals:
                                # Simple execution simulation
                                # Assume fill at entry_price
                                price = signal.entry_price
                                qty = signal.instrument.lot_size
                                cost = price * qty

                                # Slippage/Comm
                                comm = 20 # Flat per order

                                mock = get_mock()
                                # Get OHLC for rest of day
                                data = mock.post_json("history", {
                                    "symbol": signal.instrument.tradingsymbol,
                                    "exchange": signal.instrument.exchange,
                                    "interval": "1m",
                                    "start_date": date.strftime("%Y-%m-%d"),
                                    "end_date": date.strftime("%Y-%m-%d")
                                })

                                pnl = 0
                                if data['status'] == 'success':
                                    df = pd.DataFrame(data['data'])
                                    if not df.empty:
                                        # Filter future candles
                                        df['time'] = pd.to_datetime(df['time'])
                                        future_df = df[df['time'] > current_time]

                                        if not future_df.empty:
                                            # Check TP/SL
                                            sl = signal.stop_loss
                                            tp = signal.take_profit_1

                                            entry_idx = 0
                                            exit_price = future_df.iloc[-1]['close'] # Default exit EOD

                                            for _, candle in future_df.iterrows():
                                                c_low = candle['low']
                                                c_high = candle['high']

                                                if signal.side == SignalSide.LONG:
                                                    if c_low <= sl:
                                                        exit_price = sl
                                                        break
                                                    if c_high >= tp:
                                                        exit_price = tp
                                                        break
                                                    pnl = (exit_price - price) * qty
                                                elif signal.side == SignalSide.SHORT:
                                                    if c_high >= sl:
                                                        exit_price = sl
                                                        break
                                                    if c_low <= tp:
                                                        exit_price = tp
                                                        break
                                                    pnl = (price - exit_price) * qty

                                            trades.append({
                                                "date": date,
                                                "symbol": signal.instrument.tradingsymbol,
                                                "entry": price,
                                                "exit": exit_price,
                                                "pnl": pnl
                                            })
                                            equity += pnl

                        except Exception as e:
                            pass # logger.error(f"Error in step: {e}")

                        current_time += timedelta(minutes=1)

                # Calculate Metrics
                total_pnl = equity - initial_equity
                win_rate = 0
                if trades:
                    wins = len([t for t in trades if t['pnl'] > 0])
                    win_rate = (wins / len(trades)) * 100

                self.results[strategy_name] = {
                    "Total PnL": total_pnl,
                    "Win Rate": win_rate,
                    "Trades": len(trades),
                    "Equity": equity
                }
                logger.info(f"   Result: PnL {total_pnl:.2f}, Win Rate {win_rate:.1f}%")

            except Exception as e:
                logger.error(f"Failed to test {adapter_cls}: {e}")

    def generate_report(self):
        # Sort by PnL
        sorted_results = sorted(self.results.items(), key=lambda x: x[1]['Total PnL'], reverse=True)

        # Markdown
        md = "# Backtest Leaderboard\n\n"
        md += f"Date Range: {self.start_date.date()} to {self.end_date.date()}\n\n"
        md += "| Rank | Strategy | Total PnL | Win Rate | Trades | Final Equity |\n"
        md += "|---|---|---|---|---|---|\n"

        for i, (name, res) in enumerate(sorted_results):
            md += f"| {i+1} | {name} | {res['Total PnL']:.2f} | {res['Win Rate']:.1f}% | {res['Trades']} | {res['Equity']:.2f} |\n"

        output_path = os.path.join(STRATEGIES_DIR, "backtest_results", "BACKTEST_LEADERBOARD.md")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, "w") as f:
            f.write(md)

        logger.info(f"Report generated at {output_path}")

        # JSON
        json_path = output_path.replace(".md", ".json")
        with open(json_path, "w") as f:
            json.dump(self.results, f, indent=4, default=str)

def load_adapters():
    adapters = []
    sys.path.append(ADAPTERS_DIR)

    for filename in os.listdir(ADAPTERS_DIR):
        if filename.endswith("_adapter.py") and not filename.startswith("__"):
            module_name = filename[:-3]
            try:
                module = importlib.import_module(module_name)
                for name, obj in inspect.getmembers(module):
                    if inspect.isclass(obj) and issubclass(obj, StrategyAdapter) and obj is not StrategyAdapter:
                        adapters.append(obj)
            except Exception as e:
                logger.warning(f"Could not load adapter {filename}: {e}")

    return adapters

if __name__ == "__main__":
    # Test last 5 days for speed in this demo
    end_date = datetime.now()
    start_date = end_date - timedelta(days=5)

    adapters = load_adapters()
    if not adapters:
        logger.error("No adapters found.")
        sys.exit(1)

    engine = SimpleBacktestEngine(start_date, end_date)
    engine.run(adapters)
    engine.generate_report()
