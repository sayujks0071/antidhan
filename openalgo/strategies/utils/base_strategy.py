import os
import sys
import time
import logging
import argparse
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Ensure openalgo root is in path before importing trading_utils (which depends on openalgo.utils)
# This handles cases where base_strategy is imported from a script in a subdirectory
try:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    strategies_dir = os.path.dirname(current_dir)
    openalgo_root = os.path.dirname(strategies_dir)
    if openalgo_root not in sys.path:
        sys.path.insert(0, openalgo_root)
except Exception:
    pass

# Import utilities
try:
    # Try relative import first (for package mode)
    from .trading_utils import (
        APIClient, PositionManager, is_market_open, calculate_intraday_vwap, normalize_symbol,
        calculate_rsi, calculate_atr, calculate_adx, analyze_volume_profile
    )
    from .symbol_resolver import SymbolResolver
except ImportError:
    # Fallback to absolute import or direct import (for script mode)
    try:
        from trading_utils import (
            APIClient, PositionManager, is_market_open, calculate_intraday_vwap, normalize_symbol,
            calculate_rsi, calculate_atr, calculate_adx, analyze_volume_profile
        )
        from symbol_resolver import SymbolResolver
    except ImportError:
        # If running from a script that didn't set path correctly
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        from trading_utils import (
            APIClient, PositionManager, is_market_open, calculate_intraday_vwap, normalize_symbol,
            calculate_rsi, calculate_atr, calculate_adx, analyze_volume_profile
        )
        from symbol_resolver import SymbolResolver

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

        # Ensure project root is in path for DB access
        self._add_project_root_to_path()

        # Load environment variables
        load_dotenv()

        # Resolve API Key
        self.api_key = self._resolve_api_key(api_key)

        # Default to 5002 to match trading_utils default, allow override via env
        self.host = host or os.getenv('OPENALGO_HOST', 'http://127.0.0.1:5002')

        if not self.api_key and not client:
             raise ValueError("API Key must be provided via argument, OPENALGO_APIKEY env var, or database.")

        self.setup_logging(log_file)

        if client:
            self.client = client
        else:
            self.client = APIClient(api_key=self.api_key, host=self.host)

        self.pm = PositionManager(self.symbol) if PositionManager else None

    def _add_project_root_to_path(self):
        """Add the openalgo root directory to sys.path to allow importing database modules."""
        try:
            # Assuming this file is in openalgo/strategies/utils/base_strategy.py
            current_dir = os.path.dirname(os.path.abspath(__file__))
            strategies_dir = os.path.dirname(current_dir)
            openalgo_root = os.path.dirname(strategies_dir)

            # Also add the parent of openalgo to allow 'from openalgo.database import ...' if needed
            # But typically we want 'from database import ...' if running inside openalgo
            if openalgo_root not in sys.path:
                sys.path.insert(0, openalgo_root)
        except Exception as e:
            # Don't fail if we can't figure out paths, just log it later if logger exists
            print(f"Warning: Could not add project root to path: {e}")

    def _resolve_api_key(self, api_key):
        """Resolve API Key from multiple sources."""
        if api_key:
            return api_key

        # 1. Try environment variables
        key = os.getenv('OPENALGO_APIKEY') or os.getenv('OPENALGO_API_KEY')
        if key:
            return key

        # 2. Try database
        try:
            from database.auth_db import get_first_available_api_key
            key = get_first_available_api_key()
            if key:
                if hasattr(self, 'logger'):
                    self.logger.info("Resolved API key from database.")
                return key
        except ImportError:
            # Database module not available or path issue
            pass
        except Exception as e:
            if hasattr(self, 'logger'):
                self.logger.warning(f"Failed to fetch API key from DB: {e}")
            else:
                print(f"Warning: Failed to fetch API key from DB: {e}")

        return None

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
        return calculate_rsi(series, period)

    def calculate_atr(self, df, period=14):
        """Calculate Average True Range."""
        return calculate_atr(df, period).iloc[-1]

    def calculate_adx(self, df, period=14):
        """Calculate ADX."""
        result = calculate_adx(df, period)
        return result.iloc[-1] if not result.empty else 0

    def calculate_intraday_vwap(self, df):
        """Calculate VWAP."""
        return calculate_intraday_vwap(df)

    def analyze_volume_profile(self, df, n_bins=20):
        """Find Point of Control (POC)."""
        return analyze_volume_profile(df, n_bins)

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

    @classmethod
    def add_arguments(cls, parser):
        """Hook for subclasses to add arguments."""
        pass

    @classmethod
    def parse_arguments(cls, args):
        """
        Hook for subclasses to extract arguments into kwargs for __init__.
        Default implementation extracts standard arguments.
        """
        # Resolve symbol if underlying is provided (requires SymbolResolver logic if used)
        symbol = args.symbol
        if hasattr(args, 'underlying') and args.underlying and not symbol:
             # This logic was previously in run_strategy of supertrend_vwap_strategy
             try:
                 resolver = SymbolResolver()
                 res = resolver.resolve({
                     'underlying': args.underlying,
                     'type': getattr(args, 'type', 'EQUITY'),
                     'exchange': getattr(args, 'exchange', 'NSE')
                 })
                 if isinstance(res, dict):
                     symbol = res.get('sample_symbol')
                 else:
                     symbol = res
                 print(f"Resolved {args.underlying} -> {symbol}")
             except Exception as e:
                 print(f"Symbol resolution failed: {e}")

        # Basic kwargs
        kwargs = {
            "symbol": symbol,
            "quantity": args.quantity,
            "api_key": args.api_key,
            "host": args.host,
            "ignore_time": args.ignore_time,
            "log_file": args.logfile
        }

        # Add exchange if available in args (it's not in standard parser but might be added)
        if hasattr(args, 'exchange') and args.exchange:
            kwargs['exchange'] = args.exchange

        return kwargs

    @classmethod
    def cli(cls):
        """Standard CLI entry point for strategies."""
        parser = cls.get_standard_parser(cls.__name__)
        cls.add_arguments(parser)
        args = parser.parse_args()

        if not args.symbol and (not hasattr(args, 'underlying') or not args.underlying):
             # Try to find symbol from class name or other means?
             # For now, just error if no symbol.
             # Subclasses can handle this in parse_arguments if they have other ways.
             pass

        # Parse arguments into kwargs for __init__
        kwargs = cls.parse_arguments(args)

        if not kwargs.get('symbol'):
             print("Error: Must provide --symbol (or --underlying if supported)")
             return

        # Instantiate
        try:
             # Filter kwargs to only pass what __init__ accepts?
             # Or rely on __init__ accepting **kwargs or the exact arguments returned by parse_arguments.
             # BaseStrategy.__init__ takes specific args. Subclasses might take more.
             # It's safest if parse_arguments returns exactly what is needed,
             # OR if we pass **kwargs and __init__ ignores extras (which python doesn't do by default).
             # Let's assume the subclass handles its arguments in __init__.
             strategy = cls(**kwargs)
             strategy.run()
        except TypeError as e:
             # Debugging help for argument mismatches
             print(f"Error instantiating strategy: {e}")
             import traceback
             traceback.print_exc()
