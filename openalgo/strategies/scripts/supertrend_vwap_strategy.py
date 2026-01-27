#!/usr/bin/env python3
"""
SuperTrend VWAP Strategy
VWAP mean reversion with volume profile analysis.
Enhanced with Volume Profile and VWAP deviation.
Now includes Position Management and Market Hour checks.
Refactored for EOD Optimization (Class-based).
"""
import os
import sys
import time
import logging
import argparse
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Add repo root to path to allow imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

try:
    from openalgo.strategies.utils.trading_utils import is_market_open, calculate_intraday_vwap, PositionManager, APIClient
except ImportError:
    # Fallback if running from a different context
    try:
        from strategies.utils.trading_utils import is_market_open, calculate_intraday_vwap, PositionManager, APIClient
    except ImportError:
        pass # Will handle gracefully in main
        api = None

# Try native import, fallback to our APIClient
try:
    from openalgo import api
except ImportError:
    api = None

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

class SuperTrendVWAPStrategy:
    def __init__(self, symbol, quantity, api_key, host, ignore_time=False):
        self.symbol = symbol
        self.quantity = quantity
        self.api_key = api_key
        self.host = host
        self.ignore_time = ignore_time

        # Optimization Parameters
        self.threshold = 77  # Modified on 2026-01-26: High rejection rate (90.0% > 70%). Lowering threshold by 3 points.
        self.stop_pct = 2.0  # Stop Loss Percentage

        self.logger = logging.getLogger(f"VWAP_{symbol}")

        # Initialize API Client
        if api:
            self.client = api(api_key=self.api_key, host=self.host)
            self.logger.info("Using Native OpenAlgo API")
        elif 'APIClient' in globals():
            self.client = APIClient(api_key=self.api_key, host=self.host)
            self.logger.info("Using Fallback API Client (httpx)")
        else:
            self.client = None
            self.logger.error("No API client available.")

        # Initialize Position Manager
        if 'PositionManager' in globals():
            self.pm = PositionManager(symbol)
        else:
            self.pm = None
            self.logger.warning("PositionManager not available. Running without position tracking.")

        self.metrics = {
            "signals": 0, "entries": 0, "exits": 0,
            "rejected": 0, "errors": 0, "pnl": 0.0,
            "wins": 0, "losses": 0
        }

    def analyze_volume_profile(self, df, n_bins=20):
        """Basic Volume Profile analysis."""
        price_min = df['low'].min()
        price_max = df['high'].max()
        bins = np.linspace(price_min, price_max, n_bins)
        df['bin'] = pd.cut(df['close'], bins=bins, labels=False)
        volume_profile = df.groupby('bin')['volume'].sum()

        if volume_profile.empty: return 0, 0
        poc_bin = volume_profile.idxmax()
        if np.isnan(poc_bin): return 0, 0
        poc_price = bins[int(poc_bin)] + (bins[1] - bins[0]) / 2
        return poc_price, volume_profile.max()

    def calculate_score(self, last, df, poc_price):
        """Calculates a signal score (0-100)."""
        score = 50 # Base score

        is_above_vwap = last['close'] > last['vwap']
        if is_above_vwap: score += 10

        is_volume_spike = last['volume'] > df['volume'].mean() * 1.5
        if is_volume_spike: score += 20

        is_above_poc = last['close'] > poc_price
        if is_above_poc: score += 10

        is_not_overextended = abs(last['vwap_dev']) < 0.02
        if is_not_overextended: score += 10

        return min(score, 100)

    def log_metrics(self):
        msg = (f"[METRICS] signals={self.metrics['signals']} entries={self.metrics['entries']} "
               f"exits={self.metrics['exits']} rejected={self.metrics['rejected']} "
               f"errors={self.metrics['errors']} pnl={self.metrics['pnl']:.2f}")
        self.logger.info(msg)

    def run(self):
        if not self.client: return

        self.logger.info(f"Starting SuperTrend VWAP for {self.symbol} | Qty: {self.quantity}")
        self.logger.info(f"Params: Threshold={self.threshold}, Stop={self.stop_pct}%")

        while True:
            try:
                if not self.ignore_time and 'is_market_open' in globals() and not is_market_open():
                    self.logger.info("Market is closed. Waiting...")
                    time.sleep(60)
                    continue

                # Fetch history
                df = self.client.history(symbol=self.symbol, exchange="NSE", interval="5m",
                                    start_date=(datetime.now()-timedelta(days=5)).strftime("%Y-%m-%d"),
                                    end_date=datetime.now().strftime("%Y-%m-%d"))

                if df.empty or not isinstance(df, pd.DataFrame):
                    self.logger.warning("No data received. Retrying...")
                    self.metrics['errors'] += 1
                    time.sleep(10)
                    continue

                # VWAP Calculation
                if 'calculate_intraday_vwap' in globals():
                    df = calculate_intraday_vwap(df)
                else:
                    df['vwap'] = (df['volume'] * (df['high'] + df['low'] + df['close']) / 3).cumsum() / df['volume'].cumsum()
                    df['vwap_dev'] = (df['close'] - df['vwap']) / df['vwap']

                last = df.iloc[-1]
                poc_price, _ = self.analyze_volume_profile(df)

                score = self.calculate_score(last, df, poc_price)

                self.metrics['signals'] += 1

                if score >= self.threshold:
                    if self.pm and not self.pm.has_position():
                        self.logger.info(f"VWAP Buy Signal for {self.symbol} | Score: {score}")

                        resp = self.client.placesmartorder(strategy="SuperTrend VWAP", symbol=self.symbol, action="BUY",
                                            exchange="NSE", price_type="MARKET", product="MIS",
                                            quantity=self.quantity, position_size=self.quantity)

                        if resp:
                            self.pm.update_position(self.quantity, last['close'], 'BUY')
                            self.metrics['entries'] += 1
                    else:
                         self.logger.debug("Signal detected but position already open.")
                else:
                    self.metrics['rejected'] += 1
                    self.logger.info(f"[REJECTED] symbol={self.symbol} score={score} reason=Score_Below_Threshold")

                # Mock Exit Logic for Simulation/Logging
                if self.pm and self.pm.has_position():
                    # Check Stop Loss
                    entry_price = self.pm.get_entry_price()
                    if entry_price and last['close'] < entry_price * (1 - self.stop_pct/100):
                         self.logger.info(f"Stop Loss Hit. Selling...")
                         # client.placesmartorder(...)
                         pnl = (last['close'] - entry_price) * self.quantity
                         self.metrics['exits'] += 1
                         self.metrics['pnl'] += pnl
                         if pnl > 0: self.metrics['wins'] += 1
                         else: self.metrics['losses'] += 1
                         self.logger.info(f"[EXIT] symbol={self.symbol} pnl={pnl:.2f}")
                         self.pm.clear_position()

                self.log_metrics()

            except KeyboardInterrupt:
                self.logger.info("Stopping strategy...")
                break
            except Exception as e:
                self.logger.error(f"Error: {e}")
                self.metrics['errors'] += 1

            time.sleep(30)

def run_strategy(args):
    """Wrapper for backward compatibility."""
    api_key = args.api_key or os.getenv('OPENALGO_APIKEY', 'demo_key')
    host = args.host or os.getenv('OPENALGO_HOST', 'http://127.0.0.1:5001')

    strategy = SuperTrendVWAPStrategy(args.symbol, args.quantity, api_key, host, args.ignore_time)
    strategy.run()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SuperTrend VWAP Strategy")
    parser.add_argument("--symbol", type=str, required=True, help="Trading Symbol (e.g., RELIANCE)")
    parser.add_argument("--quantity", type=int, default=10, help="Order Quantity")
    parser.add_argument("--api_key", type=str, help="OpenAlgo API Key")
    parser.add_argument("--host", type=str, help="OpenAlgo Server Host")
    parser.add_argument("--ignore_time", action="store_true", help="Ignore market hours check")

    args = parser.parse_args()
    run_strategy(args)
