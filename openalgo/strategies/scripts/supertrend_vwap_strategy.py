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
script_dir = os.path.dirname(os.path.abspath(__file__))
strategies_dir = os.path.dirname(script_dir)
utils_dir = os.path.join(strategies_dir, 'utils')

# Add utils directory to path for imports
sys.path.insert(0, utils_dir)

try:
    from trading_utils import is_market_open, calculate_intraday_vwap, PositionManager, APIClient
except ImportError:
    try:
        # Try absolute import
        sys.path.insert(0, strategies_dir)
        from utils.trading_utils import is_market_open, calculate_intraday_vwap, PositionManager, APIClient
    except ImportError:
        try:
            from openalgo.strategies.utils.trading_utils import is_market_open, calculate_intraday_vwap, PositionManager, APIClient
        except ImportError:
            print("Warning: openalgo package not found or imports failed.")
            APIClient = None
            PositionManager = None
            is_market_open = lambda: True
            # Fallback implementation of calculate_intraday_vwap
            def calculate_intraday_vwap(df):
                """Fallback VWAP calculation"""
                df = df.copy()
                if 'datetime' not in df.columns:
                    if isinstance(df.index, pd.DatetimeIndex):
                        df['datetime'] = df.index
                    elif 'timestamp' in df.columns:
                        df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
                    else:
                        df['datetime'] = pd.to_datetime(df.index)
                df['datetime'] = pd.to_datetime(df['datetime'])
                df['date'] = df['datetime'].dt.date
                typical_price = (df['high'] + df['low'] + df['close']) / 3
                df['pv'] = typical_price * df['volume']
                df['cum_pv'] = df.groupby('date')['pv'].cumsum()
                df['cum_vol'] = df.groupby('date')['volume'].cumsum()
                df['vwap'] = df['cum_pv'] / df['cum_vol']
                df['vwap_dev'] = (df['close'] - df['vwap']) / df['vwap']
                return df

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
            # Normalize sector symbol (NIFTY BANK -> BANKNIFTY, NIFTYBANK -> BANKNIFTY)
            sector_symbol = self.sector_benchmark.replace(" ", "").upper()
            if "BANK" in sector_symbol and "NIFTY" in sector_symbol:
                sector_symbol = "BANKNIFTY"
            elif "NIFTY" in sector_symbol:
                sector_symbol = "NIFTY"
            else:
                sector_symbol = "NIFTY"  # Default
            
            # Fetch Sector Data
            end = datetime.now().strftime("%Y-%m-%d")
            start = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
            # Use NSE_INDEX for index symbols
            exchange = "NSE_INDEX"
            df = self.client.history(symbol=sector_symbol, interval="D", exchange=exchange, start_date=start, end_date=end)

            if not df.empty and len(df) >= 2:
                # Check 5 day trend
                if df.iloc[-1]['close'] > df.iloc[-5]['close']:
                    return True # Uptrend
            return False # Neutral or Downtrend
        except:
            return True # Fail open if sector data missing

    def run(self):
        # Normalize symbol (NIFTYBANK -> BANKNIFTY, NIFTY 50 -> NIFTY, NIFTY50 -> NIFTY)
        original_symbol = self.symbol
        symbol_upper = self.symbol.upper().replace(" ", "")
        if "BANK" in symbol_upper and "NIFTY" in symbol_upper:
            self.symbol = "BANKNIFTY"
        elif "NIFTY" in symbol_upper:
            # Remove "50" suffix if present (NIFTY50 -> NIFTY)
            self.symbol = "NIFTY" if symbol_upper.replace("50", "") == "NIFTY" else "NIFTY"
        else:
            self.symbol = original_symbol
        
        if original_symbol != self.symbol:
            self.logger.info(f"Symbol normalized: {original_symbol} -> {self.symbol}")
        
        self.logger.info(f"Starting SuperTrend VWAP for {self.symbol}")

        while True:
            try:
                if not self.ignore_time and not is_market_open():
                    time.sleep(60)
                    continue

                # Fetch history - Use NSE_INDEX for NIFTY index
                exchange = "NSE_INDEX" if "NIFTY" in self.symbol.upper() else "NSE"
                try:
                    df = self.client.history(
                        symbol=self.symbol,
                        interval="5m",
                        exchange=exchange,
                        start_date=(datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d"),
                        end_date=datetime.now().strftime("%Y-%m-%d"),
                    )
                except Exception as e:
                    self.logger.error(f"Failed to fetch history for {self.symbol} on {exchange}: {e}", exc_info=True)
                    time.sleep(60)
                    continue

                if df.empty or len(df) < 50:
                    self.logger.warning(f"Insufficient data for {self.symbol}: {len(df)} rows. Need at least 50.")
                    time.sleep(60)
                    continue
                
                # Verify required columns exist
                required_cols = ['open', 'high', 'low', 'close', 'volume']
                missing_cols = [col for col in required_cols if col not in df.columns]
                if missing_cols:
                    self.logger.error(f"Missing required columns for {self.symbol}: {missing_cols}")
                    time.sleep(60)
                    continue

                # Ensure datetime column exists and is parsed for VWAP calc
                if "datetime" in df.columns:
                    df["datetime"] = pd.to_datetime(df["datetime"])
                elif "timestamp" in df.columns:
                    df["datetime"] = pd.to_datetime(df["timestamp"])
                else:
                    df["datetime"] = pd.to_datetime(df.index)
                df = df.sort_values("datetime")

                try:
                    # Verify calculate_intraday_vwap is callable
                    if not callable(calculate_intraday_vwap):
                        self.logger.error("calculate_intraday_vwap is not callable. Check imports.")
                        time.sleep(60)
                        continue
                    df = calculate_intraday_vwap(df)
                    # Verify VWAP columns exist
                    if 'vwap' not in df.columns or 'vwap_dev' not in df.columns:
                        self.logger.error("VWAP calculation failed - missing required columns")
                        time.sleep(60)
                        continue
                except Exception as e:
                    self.logger.error(f"VWAP calc failed: {e}", exc_info=True)
                    time.sleep(60)
                    continue
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
                self.logger.error(f"Error in SuperTrend VWAP strategy for {self.symbol}: {e}", exc_info=True)

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
