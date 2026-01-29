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
    from openalgo.strategies.utils.symbol_resolver import SymbolResolver
except ImportError:
    print("Warning: openalgo package not found or imports failed.")
    APIClient = None
    PositionManager = None
    SymbolResolver = None
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
        self.threshold = 155
        self.stop_pct = 1.8

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
            # Look back 7 days to ensure 5 trading days are available
            start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            df = self.client.history(symbol=self.sector_benchmark, interval="day", start_date=start, end_date=end)

            if not df.empty and len(df) >= 5:
                # Check 5 day trend
                if df.iloc[-1]['close'] > df.iloc[-5]['close']:
                    return True # Uptrend
            return False # Neutral or Downtrend
        except Exception as e:
            self.logger.error(f"Sector check failed: {e}")
            return True # Fail open if sector data missing

    def get_vix(self):
        # Simulated VIX for dynamic deviation
        # Ideally fetch 'INDIA VIX'
        return 15.0 # Default

    def run(self):
        self.logger.info(f"Starting SuperTrend VWAP for {self.symbol}")

        while True:
            try:
                if not self.ignore_time and not is_market_open():
                    time.sleep(60)
                    continue

                # Fetch history
                # Look back 7 days to ensure sufficient data
                df = self.client.history(symbol=self.symbol, interval="5m",
                                    start_date=(datetime.now()-timedelta(days=7)).strftime("%Y-%m-%d"),
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

                # Dynamic Deviation based on VIX
                vix = self.get_vix()
                dev_threshold = 0.02
                if vix > 20:
                    dev_threshold = 0.01 # Tighten in high volatility
                elif vix < 12:
                    dev_threshold = 0.03 # Loosen in low volatility

                # Logic
                is_above_vwap = last['close'] > last['vwap']
                # Exclude current candle from mean calculation to avoid bias
                avg_volume = df['volume'].iloc[:-1].mean()
                is_volume_spike = last['volume'] > avg_volume * (self.threshold / 100.0)
                is_above_poc = last['close'] > poc_price
                is_not_overextended = abs(last['vwap_dev']) < dev_threshold

                if self.pm and self.pm.has_position():
                    pass
                else:
                    if is_above_vwap and is_volume_spike and is_above_poc and is_not_overextended and sector_bullish:
                        self.logger.info(f"VWAP Crossover Buy. POC: {poc_price:.2f}, Sector: Bullish, Dev: {last['vwap_dev']:.4f}")
                        if self.pm:
                            self.pm.update_position(self.quantity, last['close'], 'BUY')

            except Exception as e:
                self.logger.error(f"Error: {e}")

            time.sleep(60)

def run_strategy():
    parser = argparse.ArgumentParser(description="SuperTrend VWAP Strategy")
    parser.add_argument("--symbol", type=str, help="Trading Symbol")
    parser.add_argument("--underlying", type=str, help="Underlying Asset (e.g. NIFTY)")
    parser.add_argument("--type", type=str, default="EQUITY", help="Instrument Type (EQUITY, FUT, OPT)")
    parser.add_argument("--exchange", type=str, default="NSE", help="Exchange")
    parser.add_argument("--quantity", type=int, default=10, help="Order Quantity")
    parser.add_argument("--api_key", type=str, default='demo_key', help="API Key")
    parser.add_argument("--host", type=str, default='http://127.0.0.1:5001', help="Host")
    parser.add_argument("--ignore_time", action="store_true", help="Ignore market hours")
    parser.add_argument("--sector", type=str, default="NIFTY BANK", help="Sector Benchmark")

    args = parser.parse_args()

    symbol = args.symbol
    if not symbol and args.underlying:
        if SymbolResolver:
            resolver = SymbolResolver()
            res = resolver.resolve({'underlying': args.underlying, 'type': args.type, 'exchange': args.exchange})
            if isinstance(res, dict):
                symbol = res.get('sample_symbol')
            else:
                symbol = res
            print(f"Resolved {args.underlying} -> {symbol}")

    if not symbol:
        print("Error: Must provide --symbol or --underlying")
        return

    strategy = SuperTrendVWAPStrategy(
        symbol=symbol,
        quantity=args.quantity,
        api_key=args.api_key,
        host=args.host,
        ignore_time=args.ignore_time,
        sector_benchmark=args.sector
    )
    strategy.run()

if __name__ == "__main__":
    run_strategy()
