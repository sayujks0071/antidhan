import os
import sys
import time
import logging
import argparse
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Import utilities
try:
    # Try relative import first (for package mode)
    from .trading_utils import APIClient, PositionManager, is_market_open, calculate_intraday_vwap, normalize_symbol
except ImportError:
    # Fallback to absolute import or direct import (for script mode)
    try:
        from trading_utils import APIClient, PositionManager, is_market_open, calculate_intraday_vwap, normalize_symbol
    except ImportError:
        # If running from a script that didn't set path correctly
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        from trading_utils import APIClient, PositionManager, is_market_open, calculate_intraday_vwap, normalize_symbol

class BaseStrategy:
    def __init__(self, name, symbol, quantity, interval="5m", exchange="NSE",
                 api_key=None, host=None, ignore_time=False, log_file=None, client=None):
        """
        Base Strategy Class for Dhan Sandbox Strategies.
        """
        self.name = name
        self.symbol = normalize_symbol(symbol)
        self.quantity = quantity
        self.interval = interval
        self.exchange = exchange
        self.ignore_time = ignore_time

        # Support both OPENALGO_APIKEY and OPENALGO_API_KEY
        self.api_key = api_key or os.getenv('OPENALGO_APIKEY') or os.getenv('OPENALGO_API_KEY')
        # Default to 5002 to match trading_utils default, allow override via env
        self.host = host or os.getenv('OPENALGO_HOST', 'http://127.0.0.1:5002')

        if not self.api_key and not client:
             raise ValueError("API Key must be provided via argument or OPENALGO_APIKEY/OPENALGO_API_KEY env var")

        self.setup_logging(log_file)

        if client:
            self.client = client
        else:
            self.client = APIClient(api_key=self.api_key, host=self.host)

        self.pm = PositionManager(self.symbol) if PositionManager else None

    def setup_logging(self, log_file=None):
        self.logger = logging.getLogger(self.name)
        self.logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        # Clear existing handlers to avoid duplication during restarts or multiple instantiations
        if self.logger.hasHandlers():
            self.logger.handlers.clear()

        # Console Handler
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        self.logger.addHandler(ch)

        # File Handler
        if log_file:
            # Ensure directory exists
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            fh = logging.FileHandler(log_file)
            fh.setFormatter(formatter)
            self.logger.addHandler(fh)

    def run(self):
        """
        Main execution loop.
        """
        self.logger.info(f"Starting {self.name} for {self.symbol}")

        while True:
            try:
                # Use split to handle NSE_INDEX -> NSE
                if not self.ignore_time and not is_market_open(self.exchange.split('_')[0]):
                    self.logger.info("Market closed. Sleeping...")
                    time.sleep(60)
                    continue

                self.cycle()

            except Exception as e:
                self.logger.error(f"Error in execution loop: {e}", exc_info=True)

            time.sleep(60)

    def cycle(self):
        """
        Override this method to implement strategy logic per cycle.
        """
        raise NotImplementedError("Strategy must implement cycle() method")

    def fetch_history(self, days=5, symbol=None, exchange=None, interval=None):
        """
        Fetch historical data with robust error handling.
        """
        target_symbol = symbol or self.symbol
        target_exchange = exchange or self.exchange
        target_interval = interval or self.interval

        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        end_date = datetime.now().strftime("%Y-%m-%d")

        try:
            df = self.client.history(
                symbol=target_symbol,
                interval=target_interval,
                exchange=target_exchange,
                start_date=start_date,
                end_date=end_date
            )

            if df.empty:
                return df

            # Standardize datetime
            if "datetime" in df.columns:
                df["datetime"] = pd.to_datetime(df["datetime"])
            elif "timestamp" in df.columns:
                df["datetime"] = pd.to_datetime(df["timestamp"])
            else:
                df["datetime"] = pd.to_datetime(df.index)

            df = df.sort_values("datetime")
            return df

        except Exception as e:
            self.logger.error(f"Failed to fetch history for {target_symbol}: {e}")
            return pd.DataFrame()

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
            self.logger.warning(f"Could not fetch VIX: {e}. Defaulting to 15.0.")
        return 15.0

    def calculate_rsi(self, series, period=14):
        """Calculate Relative Strength Index."""
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def calculate_atr(self, df, period=14):
        """Calculate Average True Range."""
        high = df['high']
        low = df['low']
        close = df['close']
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(period).mean().iloc[-1]

    def calculate_adx(self, df, period=14):
        """Calculate ADX."""
        try:
            plus_dm = df['high'].diff()
            minus_dm = df['low'].diff()
            plus_dm[plus_dm < 0] = 0
            minus_dm[minus_dm > 0] = 0

            tr1 = df['high'] - df['low']
            tr2 = (df['high'] - df['close'].shift(1)).abs()
            tr3 = (df['low'] - df['close'].shift(1)).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

            atr = tr.rolling(period).mean()
            plus_di = 100 * (plus_dm.ewm(alpha=1/period).mean() / atr)
            minus_di = 100 * (minus_dm.abs().ewm(alpha=1/period).mean() / atr)
            dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
            adx = dx.rolling(period).mean().iloc[-1]
            return 0 if np.isnan(adx) else adx
        except:
            return 0

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

    @staticmethod
    def get_standard_parser(description="Strategy"):
        """Get a standard ArgumentParser with common arguments."""
        parser = argparse.ArgumentParser(description=description)
        parser.add_argument("--symbol", type=str, help="Trading Symbol")
        parser.add_argument("--quantity", type=int, default=10, help="Order Quantity")
        parser.add_argument("--api_key", type=str, help="API Key")
        parser.add_argument("--host", type=str, help="Host")
        parser.add_argument("--ignore_time", action="store_true", help="Ignore market hours")
        parser.add_argument("--logfile", type=str, help="Log file path")
        return parser
