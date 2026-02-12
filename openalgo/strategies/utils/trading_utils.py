import json
import logging
import os
import time
import time as time_module
from datetime import datetime
from datetime import time as dt_time
from functools import lru_cache
from pathlib import Path
import pickle
import hashlib

import httpx
import numpy as np
import pandas as pd
import pytz

from utils import httpx_client

# Configure logging
try:
    from openalgo_observability.logging_setup import setup_logging

    setup_logging()
except ImportError:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
logger = logging.getLogger("TradingUtils")


def normalize_symbol(symbol):
    """
    Normalize symbol for indices (NIFTY/BANKNIFTY).
    Example: 'NIFTY 50' -> 'NIFTY', 'BANK NIFTY' -> 'BANKNIFTY'
    """
    if not symbol:
        return symbol

    s = symbol.upper().replace(" ", "")

    if "BANK" in s and "NIFTY" in s:
        return "BANKNIFTY"

    if s == "NIFTY" or s == "NIFTY50":
        return "NIFTY"

    return symbol


def is_mcx_market_open():
    """
    Check if MCX market is open (09:00 - 23:30 IST) on weekdays.
    """
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)

    # Check weekend
    if now.weekday() >= 5:  # 5=Sat, 6=Sun
        return False

    market_start = dt_time(9, 0)
    market_end = dt_time(23, 30)
    current_time = now.time()

    return market_start <= current_time <= market_end


def is_market_open(exchange="NSE"):
    """
    Check if market is open based on exchange.
    NSE: 09:15 - 15:30 IST
    MCX: 09:00 - 23:30 IST
    """
    if exchange == "MCX":
        return is_mcx_market_open()

    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)

    # Check weekend
    if now.weekday() >= 5:  # 5=Sat, 6=Sun
        return False

    market_start = dt_time(9, 15)
    market_end = dt_time(15, 30)
    current_time = now.time()

    return market_start <= current_time <= market_end


def calculate_intraday_vwap(df):
    """
    Calculate VWAP resetting daily.
    Expects DataFrame with 'datetime' (or index), 'close', 'high', 'low', 'volume'.
    """
    df = df.copy()

    # Handle datetime column or index
    if isinstance(df.index, pd.DatetimeIndex):
        df["datetime"] = df.index
    elif "datetime" not in df.columns and "timestamp" in df.columns:
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="s")
    elif "datetime" not in df.columns:
        # If no datetime info, create from index if it's numeric (Unix timestamp)
        if df.index.dtype in ["int64", "float64"]:
            df["datetime"] = pd.to_datetime(df.index, unit="s")
        else:
            df["datetime"] = pd.to_datetime(df.index)

    # Ensure datetime is datetime object
    df["datetime"] = pd.to_datetime(df["datetime"])
    df["date"] = df["datetime"].dt.date

    # Typical Price
    df["tp"] = (df["high"] + df["low"] + df["close"]) / 3
    df["pv"] = df["tp"] * df["volume"]

    # Group by Date and calculate cumulative sums
    df["cum_pv"] = df.groupby("date")["pv"].cumsum()
    df["cum_vol"] = df.groupby("date")["volume"].cumsum()

    df["vwap"] = df["cum_pv"] / df["cum_vol"]

    # Deviation
    df["vwap_dev"] = (df["close"] - df["vwap"]) / df["vwap"]

    return df


def calculate_rsi(series, period=14):
    """Calculate Relative Strength Index."""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def calculate_atr(df, period=14):
    """Calculate Average True Range (Returns Series)."""
    high = df['high']
    low = df['low']
    close = df['close']
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def calculate_bollinger_bands(series, window=20, num_std=2):
    """
    Calculate Bollinger Bands.
    Returns: sma, upper, lower
    """
    sma = series.rolling(window=window).mean()
    std = series.rolling(window=window).std()
    upper = sma + (std * num_std)
    lower = sma - (std * num_std)
    return sma, upper, lower


def calculate_adx(df, period=14):
    """Calculate ADX (Returns Series)."""
    try:
        # Cleaned up implementation to avoid SettingWithCopyWarning and potential errors
        plus_dm = df['high'].diff()
        minus_dm = df['low'].diff()

        # Vectorized modification
        plus_dm = np.where(plus_dm < 0, 0, plus_dm)
        # If low goes UP (diff > 0), then downward movement is 0.
        # If low goes DOWN (diff < 0), then downward movement is negative.
        # BaseStrategy used: minus_dm[minus_dm > 0] = 0.
        # This keeps negative values (downward moves).
        minus_dm = np.where(minus_dm > 0, 0, minus_dm)

        tr1 = df['high'] - df['low']
        tr2 = (df['high'] - df['close'].shift(1)).abs()
        tr3 = (df['low'] - df['close'].shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        atr = tr.rolling(period).mean()

        plus_dm_series = pd.Series(plus_dm, index=df.index)
        minus_dm_series = pd.Series(minus_dm, index=df.index)

        plus_di = 100 * (plus_dm_series.ewm(alpha=1/period).mean() / atr)
        minus_di = 100 * (minus_dm_series.abs().ewm(alpha=1/period).mean() / atr)

        dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
        adx = dx.rolling(period).mean()
        return adx.fillna(0)
    except Exception:
        return pd.Series(0, index=df.index)


def analyze_volume_profile(df, n_bins=20):
    """Find Point of Control (POC)."""
    price_min = df['low'].min()
    price_max = df['high'].max()
    if price_min == price_max:
        return 0, 0
    bins = np.linspace(price_min, price_max, n_bins)

    df = df.copy()
    df['bin'] = pd.cut(df['close'], bins=bins, labels=False)
    volume_profile = df.groupby('bin')['volume'].sum()

    if volume_profile.empty:
        return 0, 0

    poc_bin = volume_profile.idxmax()
    poc_volume = volume_profile.max()
    if pd.isna(poc_bin):
        return 0, 0

    poc_bin = int(poc_bin)
    if poc_bin >= len(bins) - 1:
        poc_bin = len(bins) - 2

    poc_price = bins[poc_bin] + (bins[1] - bins[0]) / 2
    return poc_price, poc_volume


def calculate_roc(series, period=10):
    """Calculate Rate of Change (ROC)."""
    return series.pct_change(periods=period)


def calculate_vix_volatility_multiplier(vix, thresholds=None):
    """
    Calculate dynamic volatility multiplier based on VIX.

    Args:
        vix (float): Current VIX value.
        thresholds (dict, optional): thresholds for VIX levels.
            Default: {
                'high': {'level': 25, 'multiplier': 0.5, 'dev_threshold': 0.012},
                'medium': {'level': 20, 'multiplier': 1.0, 'dev_threshold': 0.025},
                'low': {'level': 12, 'multiplier': 1.0, 'dev_threshold': 0.04},
                'default': {'multiplier': 1.0, 'dev_threshold': 0.03}
            }

    Returns:
        tuple: (size_multiplier, dev_threshold)
    """
    if thresholds is None:
        thresholds = {
            'high': {'level': 25, 'multiplier': 0.5, 'dev_threshold': 0.012},
            'medium': {'level': 20, 'multiplier': 1.0, 'dev_threshold': 0.025},
            'low': {'level': 12, 'multiplier': 1.0, 'dev_threshold': 0.04},
            'default': {'multiplier': 1.0, 'dev_threshold': 0.03}
        }

    if vix > thresholds['high']['level']:
        return thresholds['high']['multiplier'], thresholds['high']['dev_threshold']
    elif vix > thresholds['medium']['level']:
        return thresholds['medium']['multiplier'], thresholds['medium']['dev_threshold']
    elif vix < thresholds['low']['level']:
        return thresholds['low']['multiplier'], thresholds['low']['dev_threshold']
    else:
        return thresholds['default']['multiplier'], thresholds['default']['dev_threshold']


class PositionManager:
    """
    Persistent position manager to track trades and prevent duplicate orders.
    Saves state to openalgo/strategies/state/{symbol}_state.json
    """

    def __init__(self, symbol):
        self.symbol = symbol
        # Determine state directory relative to this file
        # this file: openalgo/strategies/utils/trading_utils.py
        # target: openalgo/strategies/state/
        self.state_dir = Path(__file__).resolve().parent.parent / "state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.state_dir / f"{self.symbol}_state.json"

        self.position = 0
        self.entry_price = 0.0
        self.pnl = 0.0

        self.load_state()

    def load_state(self):
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    data = json.load(f)
                    self.position = data.get("position", 0)
                    self.entry_price = data.get("entry_price", 0.0)
                    self.pnl = data.get("pnl", 0.0)
                    logger.info(
                        f"Loaded state for {self.symbol}: Pos={self.position} @ {self.entry_price}"
                    )
            except Exception as e:
                logger.error(f"Failed to load state for {self.symbol}: {e}")

    def save_state(self):
        try:
            data = {
                "position": self.position,
                "entry_price": self.entry_price,
                "pnl": self.pnl,
                "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            with open(self.state_file, "w") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save state for {self.symbol}: {e}")

    def update_position(self, qty, price, side):
        """
        Update position state.
        side: 'BUY' or 'SELL'
        """
        side = side.upper()

        if side == "BUY":
            if self.position == 0:
                self.entry_price = price  # Long Entry
            elif self.position < 0:
                # Closing Short
                realized_pnl = (self.entry_price - price) * qty
                self.pnl += realized_pnl
                logger.info(f"Closed Short. PnL: {realized_pnl}")

            self.position += qty

        elif side == "SELL":
            if self.position == 0:
                self.entry_price = price  # Short Entry
            elif self.position > 0:
                # Closing Long
                realized_pnl = (price - self.entry_price) * qty
                self.pnl += realized_pnl
                logger.info(f"Closed Long. PnL: {realized_pnl}")

            self.position -= qty

        if self.position == 0:
            self.entry_price = 0.0

        logger.info(
            f"Position Updated for {self.symbol}: {self.position} @ {self.entry_price}"
        )
        self.save_state()

    def calculate_risk_adjusted_quantity(self, capital, risk_per_trade_pct, volatility, price):
        """
        Calculate position size based on Volatility (ATR).
        Encourages using Monthly ATR for robustness.

        Formula: Qty = (Capital * RiskPct) / (Volatility * 2.0)
        """
        if volatility <= 0 or price <= 0:
            logger.warning(f"Invalid Volatility ({volatility}) or Price ({price}) for sizing.")
            return 0

        risk_amount = capital * (risk_per_trade_pct / 100.0)
        stop_loss_dist = volatility * 2.0

        if stop_loss_dist == 0:
            qty = 0
        else:
            qty = risk_amount / stop_loss_dist

        # Max quantity based on capital = capital / price
        max_qty_capital = capital / price
        qty = min(qty, max_qty_capital)

        return int(qty)

    def calculate_adaptive_quantity(self, capital, risk_per_trade_pct, atr, price):
        """
        Calculate position size based on ATR (Legacy/Intraday).
        Delegates to calculate_risk_adjusted_quantity.
        """
        qty = self.calculate_risk_adjusted_quantity(capital, risk_per_trade_pct, atr, price)
        return qty

    def calculate_adaptive_quantity_monthly_atr(self, capital, risk_per_trade_pct, monthly_atr, price):
        """
        Calculate position size based on Monthly ATR.
        Alias for calculate_risk_adjusted_quantity with specific logging.
        """
        qty = self.calculate_risk_adjusted_quantity(capital, risk_per_trade_pct, monthly_atr, price)
        logger.info(f"Adaptive Sizing (Monthly ATR): Price={price}, MATR={monthly_atr:.2f}, RiskAmt={capital*risk_per_trade_pct/100:.2f}, Qty={qty}")
        return qty

    def has_position(self):
        return self.position != 0

    def get_pnl(self, current_price):
        """Calculate Unrealized PnL."""
        if self.position == 0:
            return 0.0

        if self.position > 0:
            return (current_price - self.entry_price) * self.position
        else:
            return (self.entry_price - current_price) * abs(self.position)


class SmartOrder:
    """
    Intelligent Order Execution logic.
    Wraps an API client to provide advanced order capabilities.
    """

    def __init__(self, api_client):
        self.client = api_client

    def place_adaptive_order(
        self,
        strategy,
        symbol,
        action,
        exchange,
        quantity,
        limit_price=None,
        product="MIS",
        urgency="MEDIUM",
    ):
        """
        Place an order adapting to market conditions.

        Args:
            urgency: 'LOW' (Passive Limit), 'MEDIUM' (Limit then Market), 'HIGH' (Market)
        """
        logger.info(
            f"SmartOrder: Placing {action} {quantity} {symbol} (Urgency: {urgency})"
        )

        order_type = "LIMIT" if limit_price else "MARKET"
        # price = limit_price if limit_price else 0

        # Override based on urgency
        if urgency == "HIGH":
            order_type = "MARKET"
            # price is already 0
        elif urgency == "LOW" and not limit_price:
            # Low urgency but no limit price provided? Fallback to Market but warn
            logger.warning(
                "SmartOrder: Low urgency requested but no limit price. Using MARKET."
            )
            order_type = "MARKET"

        # In a real async system, we would:
        # 1. Place Limit at Bid/Ask
        # 2. Wait 5s
        # 3. Check fill
        # 4. Cancel & Replace if not filled

        # Since this is a synchronous/blocking call in this architecture:
        # We rely on the 'smartorder' endpoint of the broker/server if available,
        # or just place the simple order.

        # However, we can simulate "Smartness" by choosing the right parameters

        try:
            # Use the client's place_smart_order if available (wrapper around placesmartorder)
            # Or use standard place_order
            if hasattr(self.client, "placesmartorder"):
                return self.client.placesmartorder(
                    strategy=strategy,
                    symbol=symbol,
                    action=action,
                    exchange=exchange,
                    price_type=order_type,
                    product=product,
                    quantity=quantity,
                    position_size=quantity,  # Simplification
                )
            else:
                logger.error("SmartOrder: Client does not support 'placesmartorder'")
                return None

        except Exception as e:
            logger.error(f"SmartOrder Failed: {e}")
            return None

    def get_pnl(self, current_price):
        if self.position == 0:
            return 0.0

        if self.position > 0:
            return (current_price - self.entry_price) * abs(self.position)
        else:
            return (self.entry_price - current_price) * abs(self.position)


class FileCache:
    def __init__(self, cache_dir=".cache/api_client_history"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_path(self, key):
        key_hash = hashlib.md5(key.encode()).hexdigest()
        return self.cache_dir / f"{key_hash}.pkl"

    def get(self, key):
        cache_path = self._get_cache_path(key)
        if cache_path.exists():
            try:
                with open(cache_path, "rb") as f:
                    logger.debug(f"Cache hit for {key}")
                    return pickle.load(f)
            except Exception as e:
                logger.warning(f"Cache read failed for {key}: {e}")
        return None

    def set(self, key, data):
        cache_path = self._get_cache_path(key)
        try:
            with open(cache_path, "wb") as f:
                pickle.dump(data, f)
        except Exception as e:
            logger.warning(f"Cache write failed for {key}: {e}")


class APIClient:
    """
    Fallback API Client using httpx if openalgo package is missing.
    """

    def __init__(self, api_key, host="http://127.0.0.1:5002"):
        self.api_key = api_key
        self.host = host.rstrip("/")
        self.cache = FileCache()
        self.quote_cache = {}  # Key: symbol, Value: (timestamp, data)
        self.quote_ttl = 1.0   # 1 second TTL

    @lru_cache(maxsize=128)
    def history(
        self,
        symbol,
        exchange="NSE",
        interval="5m",
        start_date=None,
        end_date=None,
        max_retries=3,
    ):
        """Fetch historical data with retry logic, exponential backoff, and in-memory caching."""
        # Check Cache first
        cache_key = f"{symbol}_{exchange}_{interval}_{start_date}_{end_date}"
        cached_df = self.cache.get(cache_key)
        if cached_df is not None and not cached_df.empty:
            # Only use cache if end_date is in the past (not today)
            today_str = datetime.now().strftime("%Y-%m-%d")
            check_date = end_date
            if isinstance(check_date, datetime):
                check_date = check_date.strftime("%Y-%m-%d")

            if check_date and check_date < today_str:
                return cached_df

        url = f"{self.host}/api/v1/history"

        # Ensure dates are serialized for JSON
        json_start = start_date
        if isinstance(json_start, datetime):
            json_start = json_start.strftime("%Y-%m-%d")

        json_end = end_date
        if isinstance(json_end, datetime):
            json_end = json_end.strftime("%Y-%m-%d")

        payload = {
            "symbol": symbol,
            "exchange": exchange,
            "interval": interval,  # Fixed: was "resolution"
            "start_date": json_start,  # Fixed: was "from"
            "end_date": json_end,  # Fixed: was "to"
            "apikey": self.api_key,
        }
        try:
            response = httpx_client.post(
                url,
                json=payload,
                timeout=30,
                max_retries=max_retries,
                backoff_factor=1.0,
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success" and "data" in data:
                    df = pd.DataFrame(data["data"])
                    if "timestamp" in df.columns:
                        df["datetime"] = pd.to_datetime(df["timestamp"], unit="s")
                    required_cols = ["open", "high", "low", "close", "volume"]
                    for col in required_cols:
                        if col not in df.columns:
                            df[col] = 0
                    logger.debug(
                        f"Successfully fetched {len(df)} rows for {symbol} on {exchange}"
                    )

                    # Save to Cache if valid and historical
                    today_str = datetime.now().strftime("%Y-%m-%d")
                    check_date = end_date
                    if isinstance(check_date, datetime):
                        check_date = check_date.strftime("%Y-%m-%d")

                    if check_date and check_date < today_str and not df.empty:
                        self.cache.set(cache_key, df)

                    return df
                else:
                    error_msg = data.get("message", "Unknown error")
                    logger.error(
                        f"History fetch failed for {symbol}: {error_msg}"
                    )
            else:
                error_text = response.text[:500] if response.text else "(empty)"
                logger.error(
                    f"History fetch failed (HTTP {response.status_code}): {error_text}"
                )
        except Exception as e:
            logger.error(f"API Error for {symbol}: {e}")

        return pd.DataFrame()

    def get_quote(self, symbol, exchange="NSE", max_retries=3):
        """
        Fetch real-time quote from Kite API via OpenAlgo.
        Supports single symbol or list of symbols (batch request).
        Includes short-lived cache (TTL=1s) to optimize loop performance.

        Args:
            symbol (str or list): Trading symbol(s) e.g., 'INFY' or ['INFY', 'TCS']
            exchange (str): Exchange (NSE, NFO, MCX)
            max_retries (int): Retry attempts

        Returns:
            dict: Quote data (single dict if str input, dict of dicts if list input) or None
        """
        # Check Cache for single symbol request
        now = time.time()
        if not isinstance(symbol, list):
            cache_key = f"{symbol}_{exchange}"
            if cache_key in self.quote_cache:
                ts, data = self.quote_cache[cache_key]
                if now - ts < self.quote_ttl:
                    return data

        url = f"{self.host}/api/v1/quotes"
        payload = {"symbol": symbol, "exchange": exchange, "apikey": self.api_key}

        try:
            response = httpx_client.post(
                url,
                json=payload,
                timeout=10,
                max_retries=max_retries,
                backoff_factor=1.0,
            )

            if response.status_code == 200:
                # Check if response has content
                if not response.text or len(response.text.strip()) == 0:
                    logger.error(
                        f"Quote API returned empty response for {symbol}"
                    )
                    return None

                try:
                    data = response.json()
                except ValueError:
                    error_text = response.text[:200] if response.text else "(empty)"
                    logger.error(
                        f"Quote API returned non-JSON for {symbol}: {error_text}"
                    )
                    return None

                if data.get("status") == "success" and "data" in data:
                    # If input was a list, return the data directly (it's a dict of symbols)
                    if isinstance(symbol, list):
                        return data["data"]

                    quote_data = data["data"]
                    # Ensure ltp is available
                    if "ltp" in quote_data:
                        # Update Cache
                        if not isinstance(symbol, list):
                            self.quote_cache[cache_key] = (now, quote_data)
                        return quote_data
                    else:
                        logger.warning(
                            f"Quote for {symbol} missing 'ltp' field. Available fields: {list(quote_data.keys())}"
                        )
                        return None
                else:
                    error_msg = data.get("message", "Unknown error")
                    logger.error(
                        f"Quote fetch failed: {error_msg}"
                    )
            else:
                error_text = response.text[:500] if response.text else "(empty)"
                logger.error(
                    f"Quote fetch failed (HTTP {response.status_code}): {error_text}"
                )
        except Exception as e:
            logger.error(f"Quote API Error for {symbol}: {e}")

        return None  # Failed to fetch quote

    def get_instruments(self, exchange="NSE", max_retries=3):
        """Fetch instruments list"""
        url = f"{self.host}/instruments/{exchange}"

        try:
            response = httpx_client.get(
                url,
                timeout=30,
                max_retries=max_retries,
                backoff_factor=1.0,
            )

            if response.status_code == 200:
                # Usually returns CSV text
                from io import StringIO

                return pd.read_csv(StringIO(response.text))
            else:
                logger.warning(
                    f"Instruments fetch failed (HTTP {response.status_code})"
                )
        except Exception as e:
            logger.error(f"Instruments fetch error: {e}")

        return pd.DataFrame()

    def placesmartorder(
        self,
        strategy,
        symbol,
        action,
        exchange,
        price_type,
        product,
        quantity,
        position_size,
    ):
        """Place smart order"""
        # Correct endpoint is /api/v1/placesmartorder (not /api/v1/smartorder)
        url = f"{self.host}/api/v1/placesmartorder"

        payload = {
            "apikey": self.api_key,
            "strategy": strategy,
            "symbol": symbol,
            "action": action,  # Fixed: was "transaction_type"
            "exchange": exchange,
            "pricetype": price_type,  # Fixed: was "order_type"
            "product": product,
            "quantity": str(quantity),  # API expects string
            "position_size": str(position_size),  # API expects string
            "price": "0",
            "trigger_price": "0",
            "disclosed_quantity": "0",
        }

        try:
            # Use shared client with retry logic
            response = httpx_client.post(
                url, json=payload, timeout=10, max_retries=3, backoff_factor=1.0
            )

            if response.status_code == 200:
                # Handle response - may be JSON or empty
                try:
                    response_data = response.json()
                    logger.info(f"[ENTRY] Order Placed: {response_data}")
                    return response_data
                except ValueError:
                    # Response is not JSON - might be empty or HTML
                    response_text = response.text[:200] if response.text else "(empty)"
                    logger.warning(
                        f"Order API returned non-JSON response (status 200): {response_text}"
                    )
                    # Return success indication even if response isn't JSON
                    return {
                        "status": "success",
                        "message": "Order placed (non-JSON response)",
                    }
            else:
                error_text = response.text[:500] if response.text else "(empty)"
                logger.error(
                    f"Order Failed (HTTP {response.status_code}): {error_text}"
                )
                return {
                    "status": "error",
                    "message": f"HTTP {response.status_code}: {error_text}",
                }
        except Exception as e:
            logger.error(f"Order API Error: {e}")
            import traceback

            logger.debug(traceback.format_exc())
            return {"status": "error", "message": str(e)}

    def get_option_chain(self, symbol, exchange="NFO", max_retries=3):
        """Fetch option chain for a symbol"""
        url = f"{self.host}/api/v1/optionchain"
        payload = {"symbol": symbol, "exchange": exchange, "apikey": self.api_key}

        try:
            response = httpx_client.post(
                url, json=payload, timeout=10, max_retries=max_retries, backoff_factor=1.0
            )
            if response.status_code == 200:
                try:
                    data = response.json()
                    if data.get("status") == "success" and "data" in data:
                        return data["data"]
                    else:
                        logger.warning(
                            f"Option Chain fetch failed: {data.get('message')}"
                        )
                except ValueError:
                    logger.warning("Option Chain API returned non-JSON")
            else:
                logger.warning(f"Option Chain API failed HTTP {response.status_code}")
        except Exception as e:
            logger.error(f"Option Chain API Error: {e}")
        return {}

    def get_option_greeks(self, symbol, expiry=None, max_retries=3):
        """Fetch option greeks"""
        url = f"{self.host}/api/v1/optiongreeks"
        payload = {"symbol": symbol, "apikey": self.api_key}
        if expiry:
            payload["expiry"] = expiry

        try:
            response = httpx_client.post(
                url, json=payload, timeout=10, max_retries=max_retries, backoff_factor=1.0
            )
            if response.status_code == 200:
                try:
                    data = response.json()
                    if data.get("status") == "success" and "data" in data:
                        return data["data"]
                except ValueError:
                    logger.warning("Greeks API returned non-JSON or invalid JSON response")
        except Exception as e:
            logger.error(f"Greeks API Error: {e}")
        return {}

    def get_vix(self):
        """Fetch INDIA VIX"""
        quote = self.get_quote("INDIA VIX", "NSE")
        if quote and "ltp" in quote:
            return float(quote["ltp"])
        # Fallback to a default or raise error?
        # For safety, return None so caller handles it
        return None


def calculate_supertrend(df, period=10, multiplier=3):
    """
    Calculate SuperTrend.
    Returns: supertrend (Series), direction (Series)
    """
    # Calculate ATR
    # Note: calculate_atr in this file returns Series
    atr = calculate_atr(df, period)

    # Basic Upper and Lower Bands
    hl2 = (df['high'] + df['low']) / 2
    basic_upperband = hl2 + (multiplier * atr)
    basic_lowerband = hl2 - (multiplier * atr)

    # SuperTrend Calculation
    # We need to iterate because current value depends on previous close and previous band
    # Using a loop for correctness (vectorized SuperTrend is complex/approximate)

    supertrend = [0] * len(df)
    direction = [1] * len(df)  # 1: Up, -1: Down

    # Convert to arrays for speed
    close_arr = df['close'].values
    bu_arr = basic_upperband.values
    bl_arr = basic_lowerband.values

    # Initialize first values
    final_upperband_val = 0
    final_lowerband_val = 0

    for i in range(1, len(df)):
        # Upper Band Logic
        if bu_arr[i] < final_upperband_val or close_arr[i - 1] > final_upperband_val:
            final_upperband_val = bu_arr[i]
        else:
            final_upperband_val = final_upperband_val  # Unchanged

        # Lower Band Logic
        if bl_arr[i] > final_lowerband_val or close_arr[i - 1] < final_lowerband_val:
            final_lowerband_val = bl_arr[i]
        else:
            final_lowerband_val = final_lowerband_val

        # Trend Direction
        # If previous trend was UP (1)
        if direction[i - 1] == 1:
            if close_arr[i] <= final_lowerband_val:
                direction[i] = -1
                supertrend[i] = final_upperband_val
            else:
                direction[i] = 1
                supertrend[i] = final_lowerband_val
        else:  # Previous trend was DOWN (-1)
            if close_arr[i] >= final_upperband_val:
                direction[i] = 1
                supertrend[i] = final_lowerband_val
            else:
                direction[i] = -1
                supertrend[i] = final_upperband_val

    return pd.Series(supertrend, index=df.index), pd.Series(direction, index=df.index)


def calculate_sma(series, period=20):
    """Calculate Simple Moving Average."""
    return series.rolling(window=period).mean()


def calculate_ema(series, period=20):
    """Calculate Exponential Moving Average."""
    return series.ewm(span=period, adjust=False).mean()


def calculate_relative_strength(df, index_df, window=10):
    """
    Calculate Relative Strength vs Index.
    Returns: float (Current Stock ROC - Current Index ROC)
    """
    if index_df.empty:
        return 0.0
    try:
        # Calculate ROC for both
        stock_roc = df['close'].pct_change(periods=window).iloc[-1]
        index_roc = index_df['close'].pct_change(periods=window).iloc[-1]
        return stock_roc - index_roc
    except Exception as e:
        logger.error(f"Relative Strength calculation failed: {e}")
        return 0.0
