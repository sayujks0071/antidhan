#!/usr/bin/env python3
"""
Nifty Smart VWAP Momentum (OpenAlgo Web UI Compatible)
Directional Momentum Strategy using Intraday VWAP and EMA crossovers.
Logic:
- Entry: 09:30 AM - 02:30 PM.
- Trend: Bullish if Spot > VWAP + Buffer AND Spot > EMA(20). Bearish if Spot < VWAP - Buffer AND Spot < EMA(20).
- Filter: PCR Confirmation (Bullish > 0.8, Bearish < 1.2).
- Execution: Buy ATM Options (Debit Strategy).
- Risk: SL 25%, TP 50%, Max Hold 30 mins.
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
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "NiftySmartVWAPMomentum")
UNDERLYING = os.getenv("UNDERLYING", "NIFTY")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "NFO")
PRODUCT = os.getenv("PRODUCT", "MIS")
QUANTITY = safe_int(os.getenv("QUANTITY", "1"))
STRIKE_COUNT = safe_int(os.getenv("STRIKE_COUNT", "10"))

# Strategy Parameters
VWAP_BUFFER = safe_float(os.getenv("VWAP_BUFFER", "10.0")) # Points above/below VWAP
EMA_PERIOD = safe_int(os.getenv("EMA_PERIOD", "20"))
ENTRY_START_TIME = os.getenv("ENTRY_START_TIME", "09:30")
ENTRY_END_TIME = os.getenv("ENTRY_END_TIME", "14:30")

# Risk Parameters
SL_PCT = safe_float(os.getenv("SL_PCT", "25.0"))
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


def calculate_indicators(df):
    """Calculates Intraday VWAP and EMA."""
    if df.empty:
        return df

    df = df.copy()

    # Ensure numeric columns
    cols = ['open', 'high', 'low', 'close', 'volume']
    for col in cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df['tp'] = (df['high'] + df['low'] + df['close']) / 3
    df['pv'] = df['tp'] * df['volume']

    # VWAP (Cumulative Sum for the day)
    # Assuming df contains only today's data or we group by date
    # Ideally for Intraday VWAP we need to reset at start of day.
    # Here we assume the fetched history is for "today" or recent enough.

    df['cum_pv'] = df['pv'].cumsum()
    df['cum_vol'] = df['volume'].cumsum()
    df['vwap'] = df['cum_pv'] / df['cum_vol']

    # EMA
    df['ema'] = df['close'].ewm(span=EMA_PERIOD, adjust=False).mean()

    return df


class NiftySmartVWAPMomentum:
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
        legs = [{
            "offset": "ATM",
            "option_type": option_type,
            "action": "BUY",
            "quantity": QUANTITY,
            "product": PRODUCT
        }]

        # API expects legs with offset (which it resolves internally if logic matches)
        # BUT OptionChainClient.optionsmultiorder in OpenAlgo usually expects specific symbols if possible,
        # or offsets if the backend supports it. The prompt example uses offsets.
        # However, to be precise, I will pass the symbol if I have resolved it,
        # but the prompt example suggests passing offsets:
        # {"offset": "OTM2", ...}
        # Wait, if I pass "offset", the backend resolves it.
        # But for tracking, I need the symbol.
        # Let's trust the backend resolution for execution, but I need to track it.
        # Actually, best practice: Resolve symbol locally (which I did above) and pass explicit symbol?
        # The prompt says: "Strategies should explicitly resolve and pass the option `symbol`... rather than relying on `offset`".
        # So I will construct the leg with the symbol.

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
                # Note: tracker.add_legs expects list of legs dicts
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
                        continue
                    else:
                        self.logger.info(format_kv(
                            spot=f"{underlying_ltp:.2f}",
                            pos="OPEN",
                            pnl="TRACKING"
                        ))

                # 5. Entry Logic
                if not self.tracker.open_legs:

                    # Time Window Check
                    ist_offset = timezone(timedelta(hours=5, minutes=30))
                    now = datetime.now(ist_offset)
                    start_dt = datetime.strptime(ENTRY_START_TIME, "%H:%M").time()
                    end_dt = datetime.strptime(ENTRY_END_TIME, "%H:%M").time()

                    if start_dt <= now.time() <= end_dt:
                        # Fetch History for Indicators (Always fetch to update Debouncer)
                        today_str = datetime.now().strftime("%Y-%m-%d")
                        hist_df = self.history_client.history(
                            symbol=UNDERLYING,
                            exchange=UNDERLYING_EXCHANGE,
                            interval="5m",
                            start_date=today_str,
                            end_date=today_str
                        )

                        if not hist_df.empty and len(hist_df) > EMA_PERIOD:
                            df = calculate_indicators(hist_df)
                            last_row = df.iloc[-1]

                            vwap = last_row.get("vwap", 0)
                            ema = last_row.get("ema", 0)

                            # PCR Calculation
                            total_ce_oi = sum(safe_int((item.get("ce") or {}).get("oi")) for item in chain)
                            total_pe_oi = sum(safe_int((item.get("pe") or {}).get("oi")) for item in chain)
                            pcr = total_pe_oi / total_ce_oi if total_ce_oi > 0 else 0

                            # Signals
                            is_bullish = (
                                underlying_ltp > (vwap + VWAP_BUFFER) and
                                underlying_ltp > ema and
                                pcr > 0.8
                            )

                            is_bearish = (
                                underlying_ltp < (vwap - VWAP_BUFFER) and
                                underlying_ltp < ema and
                                pcr < 1.2
                            )

                            self.logger.info(format_kv(
                                spot=f"{underlying_ltp:.2f}",
                                vwap=f"{vwap:.2f}",
                                ema=f"{ema:.2f}",
                                pcr=f"{pcr:.2f}",
                                signal="BULLISH" if is_bullish else "BEARISH" if is_bearish else "NEUTRAL"
                            ))

                            # Debounced Entry
                            bullish_signal = self.debouncer.edge("bullish_entry", is_bullish)
                            bearish_signal = self.debouncer.edge("bearish_entry", is_bearish)

                            if self.limiter.allow():
                                if bullish_signal:
                                    self._open_position(chain, "BULLISH", f"Spot > VWAP+{VWAP_BUFFER} & EMA")
                                elif bearish_signal:
                                    self._open_position(chain, "BEARISH", f"Spot < VWAP-{VWAP_BUFFER} & EMA")

                        else:
                            self.logger.info("Insufficient history for indicators.")
                    else:
                        pass

            except Exception as e:
                self.logger.error(f"Error: {e}", exc_info=True)

            time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    strategy = NiftySmartVWAPMomentum()
    strategy.run()
