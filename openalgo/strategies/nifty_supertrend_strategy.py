#!/usr/bin/env python3
"""
Nifty SuperTrend Strategy (OpenAlgo Web UI Compatible)
Trend Following Strategy using SuperTrend (10, 3) and RSI (14) Confirmation.
Logic:
- Entry: 09:15 AM - 02:30 PM.
- Trend: Bullish if Price > SuperTrend AND RSI > 50. Bearish if Price < SuperTrend AND RSI < 50.
- Execution: Buy ATM Options (Debit Strategy).
- Risk: SL 20%, TP 50%, Max Hold 30 mins, or Trend Reversal Exit.
"""
import os
import sys
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone

# Line-buffered output (required for real-time log capture)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)

# Path setup for utility imports
script_dir = os.path.dirname(os.path.abspath(__file__))
strategies_dir = os.path.dirname(script_dir)
utils_dir = os.path.join(strategies_dir, "utils")
sys.path.insert(0, utils_dir)

# Also add strategies/utils explicitly
strategy_utils_dir = os.path.join(script_dir, "utils")
sys.path.insert(0, strategy_utils_dir)

try:
    from optionchain_utils import (
        OptionChainClient,
        OptionPositionTracker,
        choose_nearest_expiry,
        is_chain_valid,
        safe_float,
        safe_int,
    )
    from strategy_common import SignalDebouncer, TradeLimiter, format_kv
except ImportError:
    print("ERROR: Could not import strategy utilities.", flush=True)
    sys.exit(1)

# Robust Market Open Check (Local Fallback to avoid dependencies)
try:
    from trading_utils import is_market_open
except ImportError:
    print("Warning: trading_utils import failed. Using local is_market_open fallback.", flush=True)
    def is_market_open():
        """Check if market is open (09:15 - 15:30 IST)."""
        # IST is UTC+5:30
        ist_offset = timezone(timedelta(hours=5, minutes=30))
        now = datetime.now(ist_offset)

        # Check weekend (5=Saturday, 6=Sunday)
        if now.weekday() >= 5:
            return False

        current_time = now.time()
        start_time = datetime.strptime("09:15", "%H:%M").time()
        end_time = datetime.strptime("15:30", "%H:%M").time()

        return start_time <= current_time <= end_time


class PrintLogger:
    def info(self, msg): print(msg, flush=True)
    def warning(self, msg): print(msg, flush=True)
    def error(self, msg, exc_info=False): print(msg, flush=True)
    def debug(self, msg): print(msg, flush=True)


# API Key retrieval
API_KEY = os.getenv("OPENALGO_APIKEY")
HOST = os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000")

root_dir = os.path.dirname(strategies_dir)
sys.path.insert(0, root_dir)

if not API_KEY:
    try:
        from database.auth_db import get_first_available_api_key
        API_KEY = get_first_available_api_key()
        if API_KEY:
            print("Successfully retrieved API Key from database.", flush=True)
    except Exception as e:
        print(f"Warning: Could not retrieve API key from database: {e}", flush=True)

if not API_KEY:
    raise ValueError("API Key must be set in OPENALGO_APIKEY environment variable")


# ===========================
# CONFIGURATION
# ===========================
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "NiftySuperTrendStrategy")
UNDERLYING = os.getenv("UNDERLYING", "NIFTY")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "NFO")
PRODUCT = os.getenv("PRODUCT", "MIS")
QUANTITY = safe_int(os.getenv("QUANTITY", "1"))
STRIKE_COUNT = safe_int(os.getenv("STRIKE_COUNT", "10"))

# Indicator Parameters
SUPERTREND_PERIOD = safe_int(os.getenv("SUPERTREND_PERIOD", "10"))
SUPERTREND_MULTIPLIER = safe_float(os.getenv("SUPERTREND_MULTIPLIER", "3.0"))
RSI_PERIOD = safe_int(os.getenv("RSI_PERIOD", "14"))

ENTRY_START_TIME = os.getenv("ENTRY_START_TIME", "09:30")
ENTRY_END_TIME = os.getenv("ENTRY_END_TIME", "14:30")

# Risk Parameters
SL_PCT = safe_float(os.getenv("SL_PCT", "20.0"))
TP_PCT = safe_float(os.getenv("TP_PCT", "50.0"))
MAX_HOLD_MIN = safe_int(os.getenv("MAX_HOLD_MIN", "30"))

# Rate Limiting
COOLDOWN_SECONDS = safe_int(os.getenv("COOLDOWN_SECONDS", "300"))
SLEEP_SECONDS = safe_int(os.getenv("SLEEP_SECONDS", "20"))
EXPIRY_REFRESH_SEC = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
MAX_ORDERS_PER_DAY = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "3"))
MAX_ORDERS_PER_HOUR = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "2"))

# Manual Expiry Override
EXPIRY_DATE = os.getenv("EXPIRY_DATE", "").strip()


class LocalHistoryClient:
    """Local client to fetch history using requests (avoiding httpx/trading_utils dependency)."""
    def __init__(self, api_key, host):
        self.api_key = api_key
        self.host = host.rstrip('/')
        self.session = requests.Session()

    def history(self, symbol, exchange, interval, start_date, end_date):
        url = f"{self.host}/api/v1/history"
        payload = {
            "apikey": self.api_key,
            "symbol": symbol,
            "exchange": exchange,
            "interval": interval,
            "start_date": start_date,
            "end_date": end_date
        }
        try:
            response = self.session.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success":
                    return pd.DataFrame(data.get("data", []))
            return pd.DataFrame()
        except Exception as e:
            print(f"History Fetch Error: {e}", flush=True)
            return pd.DataFrame()


def calculate_rsi(df, period=14):
    """Calculates RSI using pandas."""
    if df.empty: return df

    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).fillna(0)
    loss = (-delta.where(delta < 0, 0)).fillna(0)

    avg_gain = gain.ewm(com=period-1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period-1, min_periods=period).mean()

    rs = avg_gain / avg_loss
    df['rsi'] = 100 - (100 / (1 + rs))
    return df


def calculate_supertrend(df, period=10, multiplier=3):
    """Calculates SuperTrend using pandas."""
    if df.empty: return df

    # ATR Calculation
    df['tr0'] = abs(df['high'] - df['low'])
    df['tr1'] = abs(df['high'] - df['close'].shift())
    df['tr2'] = abs(df['low'] - df['close'].shift())
    df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
    df['atr'] = df['tr'].ewm(alpha=1/period, adjust=False).mean()

    # Basic Bands
    hl2 = (df['high'] + df['low']) / 2
    df['basic_upper'] = hl2 + (multiplier * df['atr'])
    df['basic_lower'] = hl2 - (multiplier * df['atr'])

    # Initialize final bands and supertrend column
    df['final_upper'] = 0.0
    df['final_lower'] = 0.0
    df['supertrend'] = True

    # Iterative calculation
    for i in range(1, len(df)):
        # Final Upper Band
        if df['basic_upper'].iloc[i] < df['final_upper'].iloc[i-1] or \
           df['close'].iloc[i-1] > df['final_upper'].iloc[i-1]:
            df.iat[i, df.columns.get_loc('final_upper')] = df['basic_upper'].iloc[i]
        else:
            df.iat[i, df.columns.get_loc('final_upper')] = df['final_upper'].iloc[i-1]

        # Final Lower Band
        if df['basic_lower'].iloc[i] > df['final_lower'].iloc[i-1] or \
           df['close'].iloc[i-1] < df['final_lower'].iloc[i-1]:
            df.iat[i, df.columns.get_loc('final_lower')] = df['basic_lower'].iloc[i]
        else:
            df.iat[i, df.columns.get_loc('final_lower')] = df['final_lower'].iloc[i-1]

        # SuperTrend Direction (True=Bullish/Green, False=Bearish/Red)
        if df['supertrend'].iloc[i-1] and df['close'].iloc[i] <= df['final_lower'].iloc[i]:
            df.iat[i, df.columns.get_loc('supertrend')] = False
        elif not df['supertrend'].iloc[i-1] and df['close'].iloc[i] >= df['final_upper'].iloc[i]:
            df.iat[i, df.columns.get_loc('supertrend')] = True
        else:
            df.iat[i, df.columns.get_loc('supertrend')] = df['supertrend'].iloc[i-1]

    return df


class NiftySuperTrendStrategy:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.history_client = LocalHistoryClient(api_key=API_KEY, host=HOST)

        # Standard Tracker for Debit Strategies (Long Options)
        self.tracker = OptionPositionTracker(
            sl_pct=SL_PCT,
            tp_pct=TP_PCT,
            max_hold_min=MAX_HOLD_MIN
        )

        self.debouncer = SignalDebouncer()
        self.limiter = TradeLimiter(
            max_per_day=MAX_ORDERS_PER_DAY,
            max_per_hour=MAX_ORDERS_PER_HOUR,
            cooldown_seconds=COOLDOWN_SECONDS
        )

        self.expiry = EXPIRY_DATE
        self.last_expiry_check = 0
        self.current_date = datetime.now().date()

        # Track active signal direction to detect reversals
        self.current_signal = None  # "BULLISH" or "BEARISH"

    def ensure_expiry(self):
        """Refresh expiry date if needed."""
        if self.expiry and (time.time() - self.last_expiry_check < EXPIRY_REFRESH_SEC):
            return

        self.logger.info("Fetching available expiry dates...")
        try:
            res = self.client.expiry(UNDERLYING, OPTIONS_EXCHANGE, "options")
            if res.get("status") == "success":
                dates = res.get("data", [])
                nearest = choose_nearest_expiry(dates)
                if nearest:
                    self.expiry = nearest
                    self.last_expiry_check = time.time()
                    self.logger.info(f"Selected expiry: {self.expiry}")
                else:
                    self.logger.warning("No valid future expiry found.")
            else:
                self.logger.error(f"Failed to fetch expiry: {res.get('message')}")
        except Exception as e:
            self.logger.error(f"Expiry fetch error: {e}")

    def _close_position(self, chain, reason):
        """Close open position."""
        self.logger.info(f"Closing position. Reason: {reason}")

        if not self.tracker.open_legs:
            return

        # Prepare exit legs (SELL to Close for Long positions)
        legs_to_close = []
        for leg in self.tracker.open_legs:
            close_leg = {
                "symbol": leg["symbol"],
                "option_type": leg["option_type"],
                "action": "SELL",  # Closing a Buy
                "quantity": leg["quantity"],
                "product": leg.get("product", PRODUCT)
            }
            legs_to_close.append(close_leg)

        try:
            res = self.client.optionsmultiorder(
                strategy=STRATEGY_NAME,
                underlying=UNDERLYING,
                exchange=OPTIONS_EXCHANGE,
                expiry_date=self.expiry,
                legs=legs_to_close
            )
            self.logger.info(f"Exit Order Response: {res}")

            if res.get("status") == "success":
                self.tracker.clear()
                self.current_signal = None
            else:
                self.logger.error(f"Exit failed: {res.get('message')}")

        except Exception as e:
            self.logger.error(f"Failed to close position: {e}")

    def _open_position(self, chain, signal_type, reason):
        """Open Long Call or Put based on signal."""
        self.logger.info(f"Attempting to enter {signal_type} ({reason})...")

        # Determine Option Type
        option_type = "CE" if signal_type == "BULLISH" else "PE"

        # Find ATM Strike
        atm_item = next((item for item in chain if (item.get("ce") or {}).get("label") == "ATM"), None)
        if not atm_item:
            self.logger.warning("ATM strike not found in chain.")
            return

        # Get Symbol and LTP
        opt_data = atm_item.get(option_type.lower(), {})
        symbol = opt_data.get("symbol")
        ltp = safe_float(opt_data.get("ltp"))

        if not symbol or ltp <= 0:
            self.logger.warning(f"Invalid symbol or LTP for {option_type}")
            return

        # Prepare Order Leg
        api_legs = [{
            "symbol": symbol, # Explicit symbol
            "option_type": option_type,
            "action": "BUY",
            "quantity": QUANTITY,
            "product": PRODUCT
        }]

        try:
            res = self.client.optionsmultiorder(
                strategy=STRATEGY_NAME,
                underlying=UNDERLYING,
                exchange=OPTIONS_EXCHANGE,
                expiry_date=self.expiry,
                legs=api_legs
            )

            if res.get("status") == "success":
                self.logger.info(f"Entry Order Success: {res}")

                # Add to Tracker
                resolved_legs = [{
                    "symbol": symbol,
                    "option_type": option_type,
                    "action": "BUY",
                    "quantity": QUANTITY,
                    "entry_price": ltp,
                    "product": PRODUCT
                }]

                self.tracker.add_legs(resolved_legs, [ltp], side="BUY")
                self.limiter.record()
                self.current_signal = signal_type
            else:
                self.logger.error(f"Entry Order Failed: {res.get('message')}")

        except Exception as e:
            self.logger.error(f"Entry execution error: {e}")

    def run(self):
        self.logger.info(f"Starting {STRATEGY_NAME} for {UNDERLYING}")

        while True:
            try:
                # 0. Daily Reset
                if datetime.now().date() != self.current_date:
                    self.current_date = datetime.now().date()
                    self.current_signal = None

                # 1. Market Hours Check
                if not is_market_open():
                    time.sleep(60)
                    continue

                # 2. Expiry Check
                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(SLEEP_SECONDS)
                    continue

                # 3. Fetch Option Chain (for Spot Price and PCR)
                chain_resp = self.client.optionchain(
                    underlying=UNDERLYING,
                    exchange=UNDERLYING_EXCHANGE,
                    expiry_date=self.expiry,
                    strike_count=STRIKE_COUNT,
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=STRIKE_COUNT)
                if not valid:
                    self.logger.warning(f"Chain invalid: {reason}")
                    time.sleep(SLEEP_SECONDS)
                    continue

                chain = chain_resp.get("chain", [])
                underlying_ltp = safe_float(chain_resp.get("underlying_ltp", 0))

                # 4. Exit Management (Priority)
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)

                    # EOD Exit
                    ist_offset = timezone(timedelta(hours=5, minutes=30))
                    now = datetime.now(ist_offset)
                    eod_time = datetime.strptime("15:15", "%H:%M").time()

                    if now.time() >= eod_time:
                        exit_now = True
                        exit_reason = "eod_sqoff"

                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(SLEEP_SECONDS)
                        # Don't continue, let it check entry logic if needed (e.g. reversal)
                        # Ideally, if exit, we wait a bit or re-evaluate.
                        # For simplicity, continue to next loop
                        continue
                    else:
                        self.logger.info(format_kv(
                            spot=f"{underlying_ltp:.2f}",
                            pos="OPEN",
                            signal=self.current_signal
                        ))

                # 5. Entry Logic
                # Fetch History (Needed for Signal Generation and Trend Reversal Check)
                ist_offset = timezone(timedelta(hours=5, minutes=30))
                now = datetime.now(ist_offset)
                today_str = datetime.now().strftime("%Y-%m-%d")
                prev_day_str = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d") # Go back 5 days to be safe for weekends

                hist_df = self.history_client.history(
                    symbol=UNDERLYING,
                    exchange=UNDERLYING_EXCHANGE,
                    interval="5m",
                    start_date=prev_day_str,
                    end_date=today_str
                )

                if not hist_df.empty and len(hist_df) > 50:
                    # Clean and Calculate Indicators
                    df = hist_df.copy()
                    cols = ['open', 'high', 'low', 'close', 'volume']
                    for col in cols:
                        df[col] = pd.to_numeric(df[col], errors='coerce')

                    df = calculate_supertrend(df, period=SUPERTREND_PERIOD, multiplier=SUPERTREND_MULTIPLIER)
                    df = calculate_rsi(df, period=RSI_PERIOD)

                    last_row = df.iloc[-1]
                    supertrend_bullish = bool(last_row.get("supertrend", False))
                    rsi_val = last_row.get("rsi", 50.0)

                    is_bullish = supertrend_bullish and (rsi_val > 50)
                    is_bearish = (not supertrend_bullish) and (rsi_val < 50)

                    self.logger.info(format_kv(
                        spot=f"{underlying_ltp:.2f}",
                        st=f"{'BULL' if supertrend_bullish else 'BEAR'}",
                        rsi=f"{rsi_val:.1f}",
                        signal="BUY_CE" if is_bullish else "BUY_PE" if is_bearish else "NEUTRAL"
                    ))

                    # 5a. Trend Reversal Exit Logic
                    if self.tracker.open_legs and self.current_signal:
                        if self.current_signal == "BULLISH" and not supertrend_bullish:
                             self._close_position(chain, "trend_reversal_bearish")
                             continue
                        elif self.current_signal == "BEARISH" and supertrend_bullish:
                             self._close_position(chain, "trend_reversal_bullish")
                             continue

                    # 5b. New Entry Logic
                    start_dt = datetime.strptime(ENTRY_START_TIME, "%H:%M").time()
                    end_dt = datetime.strptime(ENTRY_END_TIME, "%H:%M").time()

                    if not self.tracker.open_legs and start_dt <= now.time() <= end_dt:
                        # Debounced Entry
                        bullish_edge = self.debouncer.edge("bullish_entry", is_bullish)
                        bearish_edge = self.debouncer.edge("bearish_entry", is_bearish)

                        if self.limiter.allow():
                            if bullish_edge:
                                self._open_position(chain, "BULLISH", f"SuperTrend Green & RSI {rsi_val:.1f} > 50")
                            elif bearish_edge:
                                self._open_position(chain, "BEARISH", f"SuperTrend Red & RSI {rsi_val:.1f} < 50")
                else:
                    self.logger.info("Insufficient history for indicators.")

            except Exception as e:
                self.logger.error(f"Error: {e}", exc_info=True)

            time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    strategy = NiftySuperTrendStrategy()
    strategy.run()
