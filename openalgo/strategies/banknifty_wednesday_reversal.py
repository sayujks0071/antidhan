#!/usr/bin/env python3
"""
Bank Nifty Wednesday Reversal Strategy - BANKNIFTY Options (OpenAlgo Web UI Compatible)
Detects overbought conditions (RSI > 75) on the Wednesday preceding Monthly Expiry ("The Reversal Day")
and initiates a Short position (Long Put) to capture profit booking.
"""
import os
import sys
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone

# Line-buffered output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)

# Path setup
script_dir = os.path.dirname(os.path.abspath(__file__))
strategies_dir = os.path.dirname(script_dir) # openalgo/
utils_dir = os.path.join(script_dir, "utils") # openalgo/strategies/utils/
sys.path.insert(0, utils_dir)
sys.path.insert(0, strategies_dir)

try:
    from optionchain_utils import (
        OptionChainClient,
        OptionPositionTracker,
        choose_monthly_expiry,
        is_chain_valid,
        safe_float,
        safe_int,
        get_atm_strike
    )
    from strategy_common import SignalDebouncer, TradeLimiter, format_kv
except ImportError:
    print("ERROR: Could not import strategy utilities.", flush=True)
    sys.exit(1)

def is_market_open():
    """
    Checks if NSE market is open (09:15 - 15:30 IST).
    Uses UTC time + 5.5 hours to avoid pytz dependency.
    """
    now_utc = datetime.now(timezone.utc)
    ist_offset = timedelta(hours=5, minutes=30)
    now_ist = now_utc + ist_offset

    if now_ist.weekday() >= 5: # Saturday/Sunday
        return False

    current_time = now_ist.time()
    market_start = datetime.strptime("09:15", "%H:%M").time()
    market_end = datetime.strptime("15:30", "%H:%M").time()

    return market_start <= current_time <= market_end

class PrintLogger:
    def info(self, msg): print(msg, flush=True)
    def warning(self, msg): print(msg, flush=True)
    def error(self, msg, exc_info=False): print(msg, flush=True)
    def debug(self, msg): print(msg, flush=True)

class HistoryClient:
    """Local client for fetching OHLCV history."""
    def __init__(self, api_key, host="http://127.0.0.1:5000"):
        self.api_key = api_key
        self.host = host.rstrip('/')
        self.session = requests.Session()

    def get_history(self, symbol, resolution="15minute", count=100):
        """Fetches history for RSI calculation."""
        # Calculate from/to timestamps
        to_date = datetime.now()
        from_date = to_date - timedelta(days=5) # 5 days back enough for 100 15m candles

        payload = {
            "apikey": self.api_key,
            "symbol": symbol,
            "resolution": resolution,
            "from": from_date.strftime("%Y-%m-%d %H:%M:%S"),
            "to": to_date.strftime("%Y-%m-%d %H:%M:%S"),
            "exchange": "NSE_INDEX" # Typically needed
        }

        try:
            url = f"{self.host}/api/v1/history"
            response = self.session.post(url, json=payload, timeout=10)
            data = response.json()

            if data.get("status") == "success":
                candles = data.get("data", [])
                if candles:
                    df = pd.DataFrame(candles)
                    # Convert columns to numeric if needed
                    cols = ['open', 'high', 'low', 'close', 'volume']
                    for col in cols:
                        if col in df.columns:
                            df[col] = pd.to_numeric(df[col], errors='coerce')
                    return df
            return pd.DataFrame()
        except Exception as e:
            print(f"History Fetch Error: {e}", flush=True)
            return pd.DataFrame()

def calculate_rsi(series, period=14):
    """Calculates RSI using pandas."""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

# Configuration
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "BankNiftyWednesdayReversal")
UNDERLYING = os.getenv("UNDERLYING", "BANKNIFTY")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "NSE")
PRODUCT = os.getenv("PRODUCT", "MIS")
QUANTITY = safe_int(os.getenv("QUANTITY", "15")) # 1 Lot

# Strategy Parameters
RSI_PERIOD = safe_int(os.getenv("RSI_PERIOD", "14"))
RSI_THRESHOLD = safe_float(os.getenv("RSI_THRESHOLD", "75.0")) # Overbought
SL_PCT = safe_float(os.getenv("SL_PCT", "20.0"))
TP_PCT = safe_float(os.getenv("TP_PCT", "40.0"))
MAX_HOLD_MIN = safe_int(os.getenv("MAX_HOLD_MIN", "60"))

# Time Filters
ENTRY_START_TIME = os.getenv("ENTRY_START_TIME", "10:00")
ENTRY_END_TIME = os.getenv("ENTRY_END_TIME", "14:30")
EXIT_TIME = os.getenv("EXIT_TIME", "15:15")

API_KEY = os.getenv("OPENALGO_APIKEY")
HOST = os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000")

if not API_KEY:
    try:
        from database.auth_db import get_first_available_api_key
        API_KEY = get_first_available_api_key()
    except Exception:
        pass

if not API_KEY:
    raise ValueError("API Key must be set in OPENALGO_APIKEY environment variable")


class BankNiftyWednesdayReversal:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.history = HistoryClient(api_key=API_KEY, host=HOST)

        self.tracker = OptionPositionTracker(
            sl_pct=SL_PCT,
            tp_pct=TP_PCT,
            max_hold_min=MAX_HOLD_MIN
        )
        self.limiter = TradeLimiter(
            max_per_day=1, # Only 1 trade per Wednesday
            max_per_hour=1,
            cooldown_seconds=300
        )
        self.debouncer = SignalDebouncer()

        self.expiry = None
        self.last_expiry_check = 0
        self.is_pre_expiry_wed = False

        self.logger.info(f"Strategy Initialized: {STRATEGY_NAME}")
        self.logger.info(format_kv(
            underlying=UNDERLYING,
            rsi_threshold=RSI_THRESHOLD,
            sl_pct=SL_PCT,
            tp_pct=TP_PCT,
            max_hold=MAX_HOLD_MIN
        ))

    def ensure_expiry_and_check_day(self):
        """
        Updates expiry and checks if today is the correct Wednesday.
        """
        now = time.time()
        if not self.expiry or (now - self.last_expiry_check > 3600):
            try:
                res = self.client.expiry(UNDERLYING, OPTIONS_EXCHANGE, "options")
                if res.get("status") == "success":
                    dates = res.get("data", [])
                    if dates:
                        self.expiry = choose_monthly_expiry(dates) # Returns DDMMMYY
                        self.last_expiry_check = now

                        if self.expiry:
                            # Parse Expiry Date
                            expiry_date = datetime.strptime(self.expiry, "%d%b%y").date()

                            # Use IST for Today's Date
                            now_utc = datetime.now(timezone.utc)
                            ist_offset = timedelta(hours=5, minutes=30)
                            today = (now_utc + ist_offset).date()

                            # Check Condition: Today is Wednesday AND Expiry is Tomorrow (Thursday)
                            # Or more robustly: Today + 1 day == Expiry
                            days_diff = (expiry_date - today).days

                            if days_diff == 1 and today.weekday() == 2: # 2 is Wednesday
                                self.is_pre_expiry_wed = True
                                self.logger.info(f"Correct Day Detected: Pre-Expiry Wednesday. Expiry: {self.expiry}")
                            else:
                                self.is_pre_expiry_wed = False
                                self.logger.debug(f"Not Pre-Expiry Wednesday. Diff: {days_diff}, Weekday: {today.weekday()}")

            except Exception as e:
                self.logger.error(f"Error fetching expiry: {e}")

    def is_time_window_open(self):
        now = datetime.now().time()
        try:
            start = datetime.strptime(ENTRY_START_TIME, "%H:%M").time()
            end = datetime.strptime(ENTRY_END_TIME, "%H:%M").time()
            return start <= now <= end
        except ValueError:
            return False

    def should_terminate(self):
        now = datetime.now().time()
        try:
            exit_time = datetime.strptime(EXIT_TIME, "%H:%M").time()
            return now >= exit_time
        except ValueError:
            return False

    def get_atm_pe(self, chain):
        """Finds ATM Put leg details."""
        atm_strike = get_atm_strike(chain)
        if not atm_strike:
            return None

        for item in chain:
            if item.get("strike") == atm_strike:
                pe = item.get("pe", {})
                if pe.get("symbol"):
                    return {
                        "symbol": pe.get("symbol"),
                        "ltp": safe_float(pe.get("ltp")),
                        "action": "BUY",
                        "quantity": QUANTITY,
                        "product": PRODUCT,
                        "strike": atm_strike
                    }
        return None

    def _close_position(self, chain, reason):
        self.logger.info(f"Closing position. Reason: {reason}")

        for leg in self.tracker.open_legs:
            try:
                # We are Long Puts, so we SELL to close
                res = self.client.placesmartorder(
                    strategy=STRATEGY_NAME,
                    symbol=leg["symbol"],
                    action="SELL",
                    exchange=OPTIONS_EXCHANGE,
                    pricetype="MARKET",
                    product=leg["product"],
                    quantity=leg["quantity"],
                    position_size=leg["quantity"]
                )
                self.logger.info(f"Exit Order: {res}")
            except Exception as e:
                self.logger.error(f"Exit failed: {e}")

        self.tracker.clear()

    def run(self):
        self.logger.info("Starting Wednesday Reversal Strategy Loop...")

        while True:
            try:
                if not is_market_open():
                    time.sleep(20)
                    continue

                self.ensure_expiry_and_check_day()

                # 1. Manage Existing Position
                if self.tracker.open_legs:
                    chain_resp = self.client.optionchain(
                        underlying=UNDERLYING,
                        exchange=UNDERLYING_EXCHANGE,
                        expiry_date=self.expiry,
                        strike_count=10
                    )
                    chain = chain_resp.get("chain", []) if chain_resp else []

                    if chain:
                        exit_now, legs, reason = self.tracker.should_exit(chain)
                        if exit_now or self.should_terminate():
                            r = reason if exit_now else "EOD"
                            self._close_position(chain, r)

                    time.sleep(10)
                    continue

                # 2. Check Signals (Only if no position AND correct day)
                if self.is_pre_expiry_wed:
                    if self.is_time_window_open() and self.limiter.allow():

                        # Fetch History and Calculate RSI
                        df = self.history.get_history(UNDERLYING, resolution="15minute")
                        if not df.empty and len(df) > RSI_PERIOD:
                            df['rsi'] = calculate_rsi(df['close'], period=RSI_PERIOD)
                            current_rsi = df['rsi'].iloc[-1]

                            self.logger.info(f"Monitoring: RSI={current_rsi:.2f}")

                            # Signal: RSI > 75 (Overbought Reversal)
                            if self.debouncer.edge("RSI_OVERBOUGHT", current_rsi > RSI_THRESHOLD):
                                self.logger.info(f"RSI Signal Detected ({current_rsi:.2f} > {RSI_THRESHOLD}). Placing Long Put Order...")

                                # Fetch Chain
                                chain_resp = self.client.optionchain(
                                    underlying=UNDERLYING,
                                    exchange=UNDERLYING_EXCHANGE,
                                    expiry_date=self.expiry,
                                    strike_count=6
                                )
                                chain = chain_resp.get("chain", [])

                                atm_pe = self.get_atm_pe(chain)

                                if atm_pe:
                                    try:
                                        res = self.client.placesmartorder(
                                            strategy=STRATEGY_NAME,
                                            symbol=atm_pe["symbol"],
                                            action="BUY",
                                            exchange=OPTIONS_EXCHANGE,
                                            pricetype="MARKET",
                                            product=PRODUCT,
                                            quantity=QUANTITY,
                                            position_size=QUANTITY
                                        )

                                        if res.get("status") == "success":
                                            self.logger.info(f"Order Success: {res}")
                                            self.limiter.record()

                                            self.tracker.add_legs(
                                                legs=[atm_pe],
                                                entry_prices=[atm_pe["ltp"]],
                                                side="BUY"
                                            )
                                        else:
                                            self.logger.error(f"Order Failed: {res.get('message')}")

                                    except Exception as e:
                                        self.logger.error(f"Execution Error: {e}")
                                else:
                                    self.logger.warning("Could not find ATM Put.")
                        else:
                            self.logger.warning("Insufficient history for RSI.")

                    time.sleep(10)
                else:
                    # Not the correct day, sleep longer
                    time.sleep(60)

            except Exception as e:
                self.logger.error(f"Loop Error: {e}")
                time.sleep(10)

if __name__ == "__main__":
    try:
        s = BankNiftyWednesdayReversal()
        s.run()
    except KeyboardInterrupt:
        pass
