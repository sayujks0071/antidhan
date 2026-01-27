#!/usr/bin/env python3
"""
SuperTrend VWAP Strategy
VWAP mean reversion with volume profile analysis.
Enhanced with Volume Profile and VWAP deviation.
Now includes Position Management and Market Hour checks.
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
        print("Error: Could not import trading_utils. Ensure you are running from the repo root or openalgo directory.")
        sys.exit(1)

# Try native import, fallback to our APIClient
try:
    from openalgo import api
except ImportError:
    api = None

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

class SuperTrendVWAPStrategy:
    def __init__(self, symbol, quantity, api_key=None, host=None, ignore_time=False):
        self.symbol = symbol
        self.quantity = quantity
        self.api_key = api_key or os.getenv('OPENALGO_APIKEY', 'demo_key')
        self.host = host or os.getenv('OPENALGO_HOST', 'http://127.0.0.1:5001')
        self.ignore_time = ignore_time

        # Optimization Parameters
        self.threshold = 155  # Modified on 2026-01-27: Low Win Rate (40.0% < 60%). Tightening filters (threshold +5).
        self.stop_pct = 1.8  # Modified on 2026-01-27: Low R:R (1.00 < 1.5). Tightening stop_pct to improve R:R.

        self.logger = logging.getLogger(f"VWAP_{symbol}")

        # Initialize API Client
        if api:
            self.client = api(api_key=self.api_key, host=self.host)
            self.logger.info("Using Native OpenAlgo API")
        else:
            self.client = APIClient(api_key=self.api_key, host=self.host)
            self.logger.info("Using Fallback API Client (httpx)")

        self.pm = PositionManager(symbol)

    def analyze_volume_profile(self, df, n_bins=20):
        """
        Basic Volume Profile analysis.
        Identify Point of Control (POC) - price level with highest volume.
        """
        price_min = df['low'].min()
        price_max = df['high'].max()

        # Create bins
        bins = np.linspace(price_min, price_max, n_bins)

        # Bucket volume into price bins
        # Using 'close' as proxy for trade price in the bin
        df['bin'] = pd.cut(df['close'], bins=bins, labels=False)

        volume_profile = df.groupby('bin')['volume'].sum()

        # Find POC Bin
        if volume_profile.empty:
            return 0, 0

        poc_bin = volume_profile.idxmax()
        poc_volume = volume_profile.max()

        # Approximate POC Price (midpoint of bin)
        if np.isnan(poc_bin):
            return 0, 0

        poc_price = bins[int(poc_bin)] + (bins[1] - bins[0]) / 2

        return poc_price, poc_volume

    def run(self):
        self.logger.info(f"Starting SuperTrend VWAP for {self.symbol} | Qty: {self.quantity} | Thr: {self.threshold} | Stop: {self.stop_pct}")

        while True:
            try:
                # Market Hour Check
                if not self.ignore_time and not is_market_open():
                    self.logger.info("Market is closed. Waiting...")
                    time.sleep(60)
                    continue

                # Fetch sufficient history for Volume Profile (last 5 days)
                df = self.client.history(symbol=self.symbol, exchange="NSE", interval="5m",
                                    start_date=(datetime.now()-timedelta(days=5)).strftime("%Y-%m-%d"),
                                    end_date=datetime.now().strftime("%Y-%m-%d"))

                if df.empty or not isinstance(df, pd.DataFrame):
                    self.logger.warning("No data received. Retrying...")
                    time.sleep(10)
                    continue

                # Calculate Intraday VWAP (resetting daily)
                df = calculate_intraday_vwap(df)
                last = df.iloc[-1]

                # Volume Profile Analysis
                poc_price, poc_vol = self.analyze_volume_profile(df)

                # Logic:
                # 1. Price crosses above VWAP
                # 2. Volume Spike (> threshold%)
                # 3. Price is above POC (Trading above value area)
                # 4. VWAP Deviation is within reasonable bounds (not overextended)

                is_above_vwap = last['close'] > last['vwap']
                # Use self.threshold (e.g. 150 means 1.5x)
                is_volume_spike = last['volume'] > df['volume'].mean() * (self.threshold / 100.0)
                is_above_poc = last['close'] > poc_price
                is_not_overextended = abs(last['vwap_dev']) < 0.02 # Within 2% of VWAP

                self.logger.debug(f"Price: {last['close']} | VWAP: {last['vwap']:.2f} | POC: {poc_price:.2f}")

                if is_above_vwap and is_volume_spike and is_above_poc and is_not_overextended:
                    if not self.pm.has_position():
                        self.logger.info(f"VWAP Crossover Buy for {self.symbol} | POC: {poc_price:.2f} | Dev: {last['vwap_dev']:.4f}")

                        # Place Order
                        resp = self.client.placesmartorder(strategy="SuperTrend VWAP", symbol=self.symbol, action="BUY",
                                            exchange="NSE", price_type="MARKET", product="MIS",
                                            quantity=self.quantity, position_size=self.quantity)

                        if resp: # Assuming resp is not None/Empty on success
                            self.pm.update_position(self.quantity, last['close'], 'BUY')
                    else:
                        self.logger.debug("Signal detected but position already open.")

                # Exit Logic (Simple stop/target or reverse) - For now just log
                # In a real strategy, checking PnL or technical exit conditions goes here.

            except KeyboardInterrupt:
                self.logger.info("Stopping strategy...")
                break
            except Exception as e:
                self.logger.error(f"Error: {e}")

            time.sleep(30)

def run_strategy(args):
    strategy = SuperTrendVWAPStrategy(
        symbol=args.symbol,
        quantity=args.quantity,
        api_key=args.api_key,
        host=args.host,
        ignore_time=args.ignore_time
    )
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
