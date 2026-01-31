#!/usr/bin/env python3
"""
SuperTrend VWAP Strategy
VWAP mean reversion with volume profile analysis, Enhanced Sector RSI Filter, and Dynamic Risk.
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
    from symbol_resolver import SymbolResolver
except ImportError:
    try:
        sys.path.insert(0, strategies_dir)
        from utils.trading_utils import is_market_open, calculate_intraday_vwap, PositionManager, APIClient
        from utils.symbol_resolver import SymbolResolver
    except ImportError:
        try:
            from openalgo.strategies.utils.trading_utils import is_market_open, calculate_intraday_vwap, PositionManager, APIClient
            from openalgo.strategies.utils.symbol_resolver import SymbolResolver
        except ImportError:
            print("Warning: openalgo package not found or imports failed.")
            APIClient = None
            PositionManager = None
            SymbolResolver = None
            is_market_open = lambda: True
            def calculate_intraday_vwap(df):
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

class SuperTrendVWAPStrategy:
    def __init__(self, symbol, quantity, api_key=None, host=None, ignore_time=False, sector_benchmark='NIFTY BANK', logfile=None):
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

        # State
        self.trailing_stop = 0.0
        self.atr = 0.0

        # Setup Logger
        self.logger = logging.getLogger(f"VWAP_{symbol}")
        self.logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        # Console Handler
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        self.logger.addHandler(ch)

        # File Handler
        if logfile:
            fh = logging.FileHandler(logfile)
            fh.setFormatter(formatter)
            self.logger.addHandler(fh)
        self.client = APIClient(api_key=self.api_key, host=self.host)
        self.pm = PositionManager(symbol) if PositionManager else None

    def generate_signal(self, df):
        """
        Generate signal for backtesting.
        Returns: 'BUY', 'SELL', 'HOLD'
        """
        if df.empty: return 'HOLD', {}, {}

        # Ensure datetime sorted
        df = df.sort_index()

        # Calculate Indicators
        try:
            df = calculate_intraday_vwap(df)
        except:
            return 'HOLD', {}, {}

        self.atr = self.calculate_atr(df)
        last = df.iloc[-1]

        # Volume Profile
        poc_price, poc_vol = self.analyze_volume_profile(df)

        # Dynamic Deviation
        vix = self.get_vix()
        dev_threshold = 0.02
        if vix > 20: dev_threshold = 0.01
        elif vix < 12: dev_threshold = 0.03

        # Logic
        is_above_vwap = last['close'] > last['vwap']

        vol_mean = df['volume'].rolling(20).mean().iloc[-1]
        vol_std = df['volume'].rolling(20).std().iloc[-1]
        dynamic_threshold = vol_mean + (1.5 * vol_std)
        is_volume_spike = last['volume'] > dynamic_threshold

        is_above_poc = last['close'] > poc_price
        is_not_overextended = abs(last['vwap_dev']) < dev_threshold

        # Sector check (Mocked for backtest usually, or passed via client)
        sector_bullish = True

        score = 0
        details = {
            'close': last['close'],
            'vwap': last['vwap'],
            'atr': self.atr,
            'poc': poc_price
        }

        if is_above_vwap and is_volume_spike and is_above_poc and is_not_overextended and sector_bullish:
            return 'BUY', 1.0, details

        # Sell Logic (Inverse for completeness?)
        # For now, just Buy based on VWAP Breakout

        return 'HOLD', 0.0, details

    def calculate_rsi(self, series, period=14):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def calculate_atr(self, df, period=14):
        high = df['high']
        low = df['low']
        close = df['close']
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(period).mean().iloc[-1]

    def analyze_volume_profile(self, df, n_bins=20):
        """Find Point of Control (POC)."""
        price_min = df['low'].min()
        price_max = df['high'].max()
        if price_min == price_max: return 0, 0
        bins = np.linspace(price_min, price_max, n_bins)
        df['bin'] = pd.cut(df['close'], bins=bins, labels=False)
        volume_profile = df.groupby('bin')['volume'].sum()

        if volume_profile.empty: return 0, 0

        poc_bin = volume_profile.idxmax()
        poc_volume = volume_profile.max()
        if np.isnan(poc_bin): return 0, 0

        poc_bin = int(poc_bin)
        if poc_bin >= len(bins)-1: poc_bin = len(bins)-2

        poc_price = bins[poc_bin] + (bins[1] - bins[0]) / 2
        return poc_price, poc_volume

    def check_sector_correlation(self):
        """Check if sector is correlated (RSI > 50)."""
        try:
            sector_symbol = self.sector_benchmark.replace(" ", "").upper()
            if "BANK" in sector_symbol and "NIFTY" in sector_symbol:
                sector_symbol = "BANKNIFTY"
            elif "NIFTY" in sector_symbol:
                sector_symbol = "NIFTY"
            else:
                sector_symbol = "NIFTY"
            end = datetime.now().strftime("%Y-%m-%d")
            start = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
            exchange = "NSE_INDEX"
            df = self.client.history(symbol=sector_symbol, interval="D", exchange=exchange, start_date=start, end_date=end)

            if not df.empty and len(df) > 15:
                df['rsi'] = self.calculate_rsi(df['close'])
                last_rsi = df.iloc[-1]['rsi']
                self.logger.info(f"Sector {self.sector_benchmark} RSI: {last_rsi:.2f}")
                return last_rsi > 50
            return True # Default to True if not enough data
        except Exception as e:
            self.logger.warning(f"Sector Check Failed: {e}")
            return True

    def get_vix(self):
        """Fetch real VIX or default to 15.0."""
        try:
            vix_df = self.client.history(
                symbol="INDIA VIX",
                exchange="NSE_INDEX",
                interval="1d",
                start_date=(datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d"),
                end_date=datetime.now().strftime("%Y-%m-%d")
            )
            if not vix_df.empty:
                vix = vix_df.iloc[-1]['close']
                self.logger.debug(f"Fetched VIX: {vix}")
                return vix
        except Exception as e:
            self.logger.warning(f"Could not fetch VIX: {e}")
        return 15.0 # Default

    def _normalize_symbol(self):
        """Normalize NIFTY/BANKNIFTY symbols."""
        original_symbol = self.symbol
        symbol_upper = self.symbol.upper().replace(" ", "")

        if "BANK" in symbol_upper and "NIFTY" in symbol_upper:
            self.symbol = "BANKNIFTY"
        elif "NIFTY" in symbol_upper:
            # Remove "50" suffix if present (NIFTY50 -> NIFTY)
            self.symbol = "NIFTY"
        else:
            self.symbol = original_symbol

        if original_symbol != self.symbol:
            self.logger.info(f"Symbol normalized: {original_symbol} -> {self.symbol}")

    def run(self):
        self._normalize_symbol()
        self.logger.info(f"Starting SuperTrend VWAP for {self.symbol}")

        while True:
            try:
                if not self.ignore_time and not is_market_open():
                    time.sleep(60)
                    continue

                exchange = "NSE_INDEX" if "NIFTY" in self.symbol.upper() or "VIX" in self.symbol.upper() else "NSE"
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
                required_cols = ['open', 'high', 'low', 'close', 'volume']
                missing_cols = [col for col in required_cols if col not in df.columns]
                if missing_cols:
                    self.logger.error(f"Missing required columns for {self.symbol}: {missing_cols}")
                    time.sleep(60)
                    continue
                if "datetime" in df.columns:
                    df["datetime"] = pd.to_datetime(df["datetime"])
                elif "timestamp" in df.columns:
                    df["datetime"] = pd.to_datetime(df["timestamp"])
                else:
                    df["datetime"] = pd.to_datetime(df.index)
                df = df.sort_values("datetime")
                try:
                    if not callable(calculate_intraday_vwap):
                        self.logger.error("calculate_intraday_vwap is not callable. Check imports.")
                        time.sleep(60)
                        continue
                    df = calculate_intraday_vwap(df)
                    if 'vwap' not in df.columns or 'vwap_dev' not in df.columns:
                        self.logger.error("VWAP calculation failed - missing required columns")
                        time.sleep(60)
                        continue
                except Exception as e:
                    self.logger.error(f"VWAP calc failed: {e}", exc_info=True)
                    time.sleep(60)
                    continue
                self.atr = self.calculate_atr(df)
                last = df.iloc[-1]

                # Volume Profile
                poc_price, poc_vol = self.analyze_volume_profile(df)

                # Dynamic Deviation based on VIX
                vix = self.get_vix()
                dev_threshold = 0.02
                size_multiplier = 1.0

                if vix > 25:
                    dev_threshold = 0.008 # Very tight in extreme volatility
                    size_multiplier = 0.5 # Reduce position size
                elif vix > 20:
                    dev_threshold = 0.015 # Tighten in high volatility
                elif vix < 12:
                    dev_threshold = 0.03 # Loosen in low volatility

                # Logic
                is_above_vwap = last['close'] > last['vwap']

                # Dynamic Volume Threshold (Mean + 1.5 StdDev)
                vol_mean = df['volume'].rolling(20).mean().iloc[-1]
                vol_std = df['volume'].rolling(20).std().iloc[-1]
                dynamic_threshold = vol_mean + (1.5 * vol_std)
                is_volume_spike = last['volume'] > dynamic_threshold

                # Volume Profile Logic: Price must be above Point of Control to confirm value migration up
                is_above_poc = last['close'] > poc_price
                is_not_overextended = abs(last['vwap_dev']) < dev_threshold

                if self.pm and self.pm.has_position():
                    # Manage Position (Trailing Stop)
                    if self.trailing_stop == 0:
                        self.trailing_stop = last['close'] - (2 * self.atr) # Initial SL

                    # Update Trailing Stop (Only move up)
                    new_stop = last['close'] - (2 * self.atr)
                    if new_stop > self.trailing_stop:
                        self.trailing_stop = new_stop
                        self.logger.info(f"Trailing Stop Updated: {self.trailing_stop:.2f}")

                    # Check Exit
                    if last['close'] < self.trailing_stop:
                        self.logger.info(f"Trailing Stop Hit at {last['close']:.2f}")
                        self.pm.update_position(self.quantity, last['close'], 'SELL')
                        self.trailing_stop = 0.0

                else:
                    # Entry Logic
                    sector_bullish = self.check_sector_correlation()

                    if is_above_vwap and is_volume_spike and is_above_poc and is_not_overextended and sector_bullish:
                        adj_qty = int(self.quantity * size_multiplier)
                        if adj_qty < 1: adj_qty = 1 # Minimum 1
                        self.logger.info(f"VWAP Crossover Buy. Price: {last['close']:.2f}, POC: {poc_price:.2f}, Vol: {last['volume']}, Sector: Bullish, Dev: {last['vwap_dev']:.4f}, Qty: {adj_qty} (VIX: {vix})")
                        if self.pm:
                            self.pm.update_position(adj_qty, last['close'], 'BUY')
                            self.trailing_stop = last['close'] - (2 * self.atr)

            except Exception as e:
                self.logger.error(f"Error in SuperTrend VWAP strategy for {self.symbol}: {e}", exc_info=True)

            time.sleep(60)

def run_strategy():
    parser = argparse.ArgumentParser(description="SuperTrend VWAP Strategy")
    parser.add_argument("--symbol", type=str, help="Trading Symbol")
    parser.add_argument("--underlying", type=str, help="Underlying Asset (e.g. NIFTY)")
    parser.add_argument("--type", type=str, default="EQUITY", help="Instrument Type (EQUITY, FUT, OPT)")
    parser.add_argument("--exchange", type=str, default="NSE", help="Exchange")
    parser.add_argument("--quantity", type=int, default=10, help="Order Quantity")
    parser.add_argument("--api_key", type=str, help="API Key (or set OPENALGO_APIKEY env var)")
    parser.add_argument("--host", type=str, default='http://127.0.0.1:5001', help="Host")
    parser.add_argument("--ignore_time", action="store_true", help="Ignore market hours")
    parser.add_argument("--sector", type=str, default="NIFTY BANK", help="Sector Benchmark")
    parser.add_argument("--logfile", type=str, help="Log file path")

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

    # Default logfile if not provided
    logfile = args.logfile
    if not logfile:
        log_dir = os.path.join(strategies_dir, "..", "log", "strategies")
        os.makedirs(log_dir, exist_ok=True)
        logfile = os.path.join(log_dir, f"{symbol}_supertrend.log")

    strategy = SuperTrendVWAPStrategy(
        symbol=symbol,
        quantity=args.quantity,
        api_key=args.api_key,
        host=args.host,
        ignore_time=args.ignore_time,
        sector_benchmark=args.sector,
        logfile=logfile
    )
    strategy.run()

# Module level wrapper for SimpleBacktestEngine
def generate_signal(df, client=None, symbol=None, params=None):
    # Instantiate strategy with dummy params
    strat = SuperTrendVWAPStrategy(symbol=symbol or "TEST", quantity=1, api_key="test", host="test")

    # Apply params if provided
    if params:
        if 'threshold' in params: strat.threshold = params['threshold']
        if 'stop_pct' in params: strat.stop_pct = params['stop_pct']

    action, score, details = strat.generate_signal(df)
    return action, score, details

if __name__ == "__main__":
    run_strategy()
