import argparse
import logging
import os
import sys
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
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
    from .symbol_resolver import SymbolResolver
    from .trading_utils import (
        APIClient,
        PositionManager,
        SmartOrder,
        analyze_volume_profile,
        calculate_adx,
        calculate_atr,
        calculate_bollinger_bands,
        calculate_ema,
        calculate_intraday_vwap,
        calculate_relative_strength,
        calculate_roc,
        calculate_rsi,
        calculate_sma,
        calculate_supertrend,
        is_market_open,
        normalize_symbol,
    )
except ImportError:
    # Fallback to absolute import or direct import (for script mode)
    try:
        from symbol_resolver import SymbolResolver
        from trading_utils import (
            APIClient,
            PositionManager,
            SmartOrder,
            analyze_volume_profile,
            calculate_adx,
            calculate_atr,
            calculate_bollinger_bands,
            calculate_ema,
            calculate_intraday_vwap,
            calculate_relative_strength,
            calculate_roc,
            calculate_rsi,
            calculate_sma,
            calculate_supertrend,
            is_market_open,
            normalize_symbol,
        )
    except ImportError:
        # If running from a script that didn't set path correctly
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        from symbol_resolver import SymbolResolver
        from trading_utils import (
            APIClient,
            PositionManager,
            SmartOrder,
            analyze_volume_profile,
            calculate_adx,
            calculate_atr,
            calculate_bollinger_bands,
            calculate_ema,
            calculate_intraday_vwap,
            calculate_relative_strength,
            calculate_roc,
            calculate_rsi,
            calculate_sma,
            calculate_supertrend,
            is_market_open,
            normalize_symbol,
        )

class BaseStrategy:
    def __init__(self, name=None, symbol=None, quantity=1, interval="5m", exchange="NSE",
                 api_key=None, host=None, ignore_time=False, log_file=None, client=None,
                 sector=None, underlying=None, type="EQUITY", product="MIS", **kwargs):
        """
        Base Strategy Class for Dhan Sandbox Strategies.
        Accepts standard parameters and kwargs for flexibility.
        """
        self.symbol = normalize_symbol(symbol) if symbol else None
        self.name = name or (f"Strategy_{self.symbol}" if self.symbol else "Strategy")
        self.quantity = quantity
        self.interval = interval
        self.exchange = exchange
        self.ignore_time = ignore_time
        self.sector = sector
        self.underlying = underlying
        self.type = type
        self.product = product

        # Set any additional kwargs as attributes (e.g. threshold, stop_pct)
        for k, v in kwargs.items():
            setattr(self, k, v)

        # Ensure project root is in path for DB access
        self._add_project_root_to_path()

        # Load environment variables
        load_dotenv()

        # Resolve API Key
        self.api_key = self._resolve_api_key(api_key)

        # Default to 5002 to match trading_utils default, allow override via env
        self.host = host or os.getenv('OPENALGO_HOST', 'http://127.0.0.1:5002')

        if not self.api_key and not client:
             # Warn but don't fail immediately, allowing for test/mock scenarios
             # However, for real trading it is required.
             if not os.getenv('PYTEST_CURRENT_TEST'):
                 print("Warning: API Key not found. Strategy may fail to connect.")

        self.setup_logging(log_file)

        if client:
            self.client = client
        else:
            self.client = APIClient(api_key=self.api_key, host=self.host)

        self.pm = PositionManager(self.symbol) if (PositionManager and self.symbol) else None
        self.smart_order = SmartOrder(self.client) if SmartOrder else None

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
            pass

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
            # Ensure project root is in path
            self._add_project_root_to_path()
            # This requires 'database' to be importable
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
                pass

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

    def execute_trade(self, action, quantity, price=None, urgency="MEDIUM"):
        """
        Execute a trade using SmartOrder and update PositionManager.
        """
        if not self.smart_order or not self.pm:
            self.logger.warning("SmartOrder or PositionManager not initialized. Cannot execute trade.")
            return None

        self.logger.info(f"Executing {action} {quantity} {self.symbol} @ {price or 'MKT'}")

        # Place order via API
        response = self.smart_order.place_adaptive_order(
            strategy=self.name,
            symbol=self.symbol,
            action=action,
            exchange=self.exchange,
            quantity=quantity,
            limit_price=price,
            product=self.product,
            urgency=urgency
        )

        # Update local position state if API call didn't fail (optimistic update or check response)
        # Note: API might return None on failure
        if response:
            # We assume success if we got a response. In a real system, we'd check 'status'
            update_price = price if price else 0 # Use 0 or fetch LTP? PositionManager handles 0?
            # If price is None (Market), we might want to fetch LTP for accurate PnL tracking
            if not update_price:
                 # Quick LTP fetch or just use 0 (PositionManager uses it for PnL)
                 quote = self.client.get_quote(self.symbol, self.exchange)
                 if quote and 'ltp' in quote:
                     update_price = float(quote['ltp'])

            self.pm.update_position(quantity, update_price, action)
            return response
        else:
            self.logger.error("Trade execution failed (no response from API)")
            return None

    def buy(self, quantity, price=None, urgency="MEDIUM"):
        """Convenience wrapper for BUY trade."""
        return self.execute_trade("BUY", quantity, price, urgency)

    def sell(self, quantity, price=None, urgency="MEDIUM"):
        """Convenience wrapper for SELL trade."""
        return self.execute_trade("SELL", quantity, price, urgency)

    def get_current_price(self):
        """Fetch current LTP for the symbol."""
        quote = self.client.get_quote(self.symbol, self.exchange)
        if quote and 'ltp' in quote:
            return float(quote['ltp'])
        return None

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

    def calculate_sma(self, series, period=20):
        """Calculate Simple Moving Average."""
        return calculate_sma(series, period)

    def calculate_ema(self, series, period=20):
        """Calculate Exponential Moving Average."""
        return calculate_ema(series, period)

    def calculate_relative_strength(self, df, index_df, period=10):
        """Calculate Relative Strength."""
        return calculate_relative_strength(df, index_df, period)

    def calculate_atr(self, df, period=14):
        """Calculate Average True Range (Scalar)."""
        return calculate_atr(df, period).iloc[-1]

    def calculate_atr_series(self, df, period=14):
        """Calculate Average True Range (Series)."""
        return calculate_atr(df, period)

    def calculate_roc(self, series, period=10):
        """Calculate Rate of Change (ROC)."""
        return calculate_roc(series, period)

    def is_lunch_break(self):
        """Avoid trading during low volume lunch hours (12:00 - 13:00)."""
        now = datetime.now()
        if 12 <= now.hour < 13:
            return True
        return False

    def get_monthly_atr(self, symbol=None):
        """
        Fetch daily data (30+ days) and calculate ATR for adaptive sizing.
        """
        try:
            target_symbol = symbol or self.symbol
            # Ensure we fetch enough data for ATR calculation (e.g. 35 days for 14 period + buffer)
            df = self.fetch_history(days=40, symbol=target_symbol, interval="D")

            if df.empty or len(df) < 15:
                self.logger.warning(f"Insufficient daily data for Monthly ATR calculation: {len(df)}")
                return 0.0

            atr_series = calculate_atr(df, period=14)
            monthly_atr = atr_series.iloc[-1]
            return monthly_atr
        except Exception as e:
            self.logger.error(f"Error calculating Monthly ATR: {e}")
            return 0.0

    def get_adaptive_quantity(self, price, risk_pct=1.0, capital=500000):
        """
        Calculate adaptive quantity based on Monthly ATR (Robust Volatility).
        Delegates to PositionManager.
        """
        if not self.pm:
            self.logger.warning("PositionManager not initialized. Returning default quantity.")
            return self.quantity

        monthly_atr = self.get_monthly_atr()
        if monthly_atr > 0:
            qty = self.pm.calculate_adaptive_quantity_monthly_atr(capital, risk_pct, monthly_atr, price)
            self.logger.info(f"Adaptive Quantity: {qty} (Monthly ATR: {monthly_atr:.2f})")
            return qty

        return self.quantity

    def calculate_adx(self, df, period=14):
        """Calculate ADX (Scalar)."""
        result = calculate_adx(df, period)
        return result.iloc[-1] if not result.empty else 0

    def calculate_adx_series(self, df, period=14):
        """Calculate ADX (Series)."""
        return calculate_adx(df, period)

    def calculate_intraday_vwap(self, df):
        """Calculate VWAP."""
        return calculate_intraday_vwap(df)

    def calculate_supertrend(self, df, period=10, multiplier=3):
        """Calculate SuperTrend."""
        return calculate_supertrend(df, period, multiplier)

    def analyze_volume_profile(self, df, n_bins=20):
        """Find Point of Control (POC)."""
        return analyze_volume_profile(df, n_bins)

    def check_sector_correlation(self, sector_benchmark=None, lookback_days=30):
        """
        Check sector correlation using RSI logic.
        """
        try:
            # Use provided sector or default to self.sector or fallback
            sector_symbol = normalize_symbol(sector_benchmark or self.sector or "NIFTY BANK")

            # Use NSE_INDEX for indices
            exchange = "NSE_INDEX" if "NIFTY" in sector_symbol.upper() or "VIX" in sector_symbol.upper() else "NSE"

            # Fetch data using the existing client
            df = self.fetch_history(days=lookback_days, symbol=sector_symbol, interval="D", exchange=exchange)

            if not df.empty and len(df) > 15:
                rsi = self.calculate_rsi(df['close'])
                last_rsi = rsi.iloc[-1]
                self.logger.info(f"Sector {sector_symbol} RSI: {last_rsi:.2f}")
                return last_rsi > 50
            return False
        except Exception as e:
            self.logger.warning(f"Sector Check Failed: {e}. Defaulting to True (Allow) to prevent blocking on data issues.")
            return True

    @staticmethod
    def get_standard_parser(description="Strategy"):
        """Get a standard ArgumentParser with common arguments."""
        parser = argparse.ArgumentParser(description=description)
        # Core
        parser.add_argument("--symbol", type=str, help="Trading Symbol")
        parser.add_argument("--quantity", type=int, default=1, help="Order Quantity")
        parser.add_argument("--interval", type=str, default="5m", help="Candle Interval")
        parser.add_argument("--exchange", type=str, default="NSE", help="Exchange")
        parser.add_argument("--product", type=str, default="MIS", help="Product Type (MIS/CNC/NRML)")

        # Connection
        parser.add_argument("--api_key", type=str, help="API Key")
        parser.add_argument("--host", type=str, help="Host URL")
        parser.add_argument("--logfile", type=str, help="Log file path")

        # Logic / Filters
        parser.add_argument("--ignore_time", action="store_true", help="Ignore market hours")
        parser.add_argument("--sector", type=str, help="Sector Benchmark (e.g., NIFTY 50)")
        parser.add_argument("--type", type=str, default="EQUITY", help="Instrument Type (EQUITY, FUT, OPT)")
        parser.add_argument("--underlying", type=str, help="Underlying Asset (e.g. NIFTY)")

        # Risk Management
        parser.add_argument("--risk", type=float, default=1.0, help="Risk Percentage")
        parser.add_argument("--sl", type=float, help="Stop Loss Percentage/Points")
        parser.add_argument("--tp", type=float, help="Take Profit Percentage/Points")

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

        # Basic kwargs from all arguments
        kwargs = vars(args).copy()

        # Ensure symbol is updated if resolved
        kwargs['symbol'] = symbol

        # Ensure defaults for key parameters if not present
        if 'exchange' not in kwargs: kwargs['exchange'] = 'NSE'
        if 'type' not in kwargs: kwargs['type'] = 'EQUITY'
        if 'sector' not in kwargs: kwargs['sector'] = None
        if 'log_file' not in kwargs: kwargs['log_file'] = kwargs.get('logfile')

        return kwargs

    @classmethod
    def cli(cls):
        """Standard CLI entry point for strategies."""
        parser = cls.get_standard_parser(cls.__name__)
        cls.add_arguments(parser)
        args, unknown = parser.parse_known_args() # Use parse_known_args to allow extra args

        # Parse arguments into kwargs for __init__
        kwargs = cls.parse_arguments(args)

        if not kwargs.get('symbol'):
             print("Error: Must provide --symbol (or --underlying if supported)")
             return

        # Instantiate
        try:
             # Create strategy instance. kwargs are passed to __init__
             strategy = cls(**kwargs)
             strategy.run()
        except TypeError as e:
             # Debugging help for argument mismatches
             print(f"Error instantiating strategy: {e}")
             import traceback
             traceback.print_exc()
