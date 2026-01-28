#!/usr/bin/env python3
"""
SuperTrend VWAP Strategy
VWAP mean reversion with volume profile analysis and Sector Correlation.
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
    print("Warning: openalgo package not found or imports failed.")
    APIClient = None
    PositionManager = None
    is_market_open = lambda: True
    calculate_intraday_vwap = lambda x: x

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

class SuperTrendVWAPStrategy:
    def __init__(self, symbol, quantity, api_key=None, host=None, ignore_time=False, sector_benchmark='NIFTY BANK'):
        self.symbol = symbol
        self.quantity = quantity
        self.api_key = api_key or os.getenv('OPENALGO_APIKEY')
        if not self.api_key:
            raise ValueError("API Key must be provided via --api_key or OPENALGO_APIKEY env var")

        self.host = host or os.getenv('OPENALGO_HOST', 'http://127.0.0.1:5001')
        self.ignore_time = ignore_time
        self.sector_benchmark = sector_benchmark

        # Optimization Parameters
        self.threshold = 155  # Modified on 2026-01-27: Low Win Rate (40.0% < 60%). Tightening filters (threshold +5).
        self.stop_pct = 1.8  # Modified on 2026-01-27: Low R:R (1.00 < 1.5). Tightening stop_pct to improve R:R.

        self.logger = logging.getLogger(f"VWAP_{symbol}")
        self.client = APIClient(api_key=self.api_key, host=self.host)
        self.pm = PositionManager(symbol) if PositionManager else None

    def analyze_volume_profile(self, df, n_bins=20):
        """Find Point of Control (POC)."""
        price_min = df['low'].min()
        price_max = df['high'].max()
        bins = np.linspace(price_min, price_max, n_bins)
        df['bin'] = pd.cut(df['close'], bins=bins, labels=False)
        volume_profile = df.groupby('bin')['volume'].sum()

        if volume_profile.empty: return 0, 0

        poc_bin = volume_profile.idxmax()
        poc_volume = volume_profile.max()
        if np.isnan(poc_bin): return 0, 0

        poc_price = bins[int(poc_bin)] + (bins[1] - bins[0]) / 2
        return poc_price, poc_volume

    def check_sector_correlation(self):
        """Check if sector is correlated (Positive Trend)."""
        try:
            # Fetch Sector Data
            end = datetime.now().strftime("%Y-%m-%d")
            start = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
            df = self.client.history(symbol=self.sector_benchmark, interval="day", start_date=start, end_date=end)

            if not df.empty and len(df) >= 2:
                # Check 5 day trend
                if df.iloc[-1]['close'] > df.iloc[-5]['close']:
                    return True # Uptrend
            return False # Neutral or Downtrend
        except:
            return True # Fail open if sector data missing

    def run(self):
        self.logger.info(f"Starting SuperTrend VWAP for {self.symbol}")

        while True:
            try:
                if not self.ignore_time and not is_market_open():
                    time.sleep(60)
                    continue

                # Fetch history
                df = self.client.history(symbol=self.symbol, interval="5m",
                                    start_date=(datetime.now()-timedelta(days=5)).strftime("%Y-%m-%d"),
                                    end_date=datetime.now().strftime("%Y-%m-%d"))

                if df.empty or len(df) < 50:
                    time.sleep(10)
                    continue

                df = calculate_intraday_vwap(df)
                last = df.iloc[-1]

                # Volume Profile
                poc_price, poc_vol = self.analyze_volume_profile(df)

                # Sector Check
                sector_bullish = self.check_sector_correlation()

                # Logic
                is_above_vwap = last['close'] > last['vwap']
                is_volume_spike = last['volume'] > df['volume'].mean() * (self.threshold / 100.0)
                is_above_poc = last['close'] > poc_price
                is_not_overextended = abs(last['vwap_dev']) < 0.02

                if self.pm and self.pm.has_position():
                    # Manage Position (Simple Stop/Target handled by PM logic usually, or here)
                    # For brevity, rely on logging or external monitor
                    pass
                else:
                    if is_above_vwap and is_volume_spike and is_above_poc and is_not_overextended and sector_bullish:
                        self.logger.info(f"VWAP Crossover Buy. POC: {poc_price:.2f}, Sector: Bullish")
                        if self.pm:
                            self.pm.update_position(self.quantity, last['close'], 'BUY')

            except Exception as e:
                self.logger.error(f"Error: {e}")

            time.sleep(60)

def run_strategy():
    parser = argparse.ArgumentParser(description="SuperTrend VWAP Strategy")
    parser.add_argument("--symbol", type=str, required=True, help="Trading Symbol")
    parser.add_argument("--quantity", type=int, default=10, help="Order Quantity")
    parser.add_argument("--api_key", type=str, default='demo_key', help="API Key")
    parser.add_argument("--host", type=str, default='http://127.0.0.1:5001', help="Host")
    parser.add_argument("--ignore_time", action="store_true", help="Ignore market hours")
    parser.add_argument("--sector", type=str, default="NIFTY BANK", help="Sector Benchmark")

    args = parser.parse_args()

    strategy = SuperTrendVWAPStrategy(
        symbol=args.symbol,
        quantity=args.quantity,
        api_key=args.api_key,
        host=args.host,
        ignore_time=args.ignore_time,
        sector_benchmark=args.sector
    )
    strategy.run()

if __name__ == "__main__":
    run_strategy()
