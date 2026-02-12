#!/usr/bin/env python3
"""
Bank Nifty HDFC Correlation Strategy - BANKNIFTY Options (OpenAlgo Web UI Compatible)
Buys BANKNIFTY Monthly Calls when HDFC Bank and ICICI Bank show strong bullish momentum.
"""
import os
import sys
import time
from datetime import datetime

# Line-buffered output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)

# Path setup
script_dir = os.path.dirname(os.path.abspath(__file__))
strategies_dir = os.path.dirname(script_dir)
utils_dir = os.path.join(strategies_dir, "utils")
sys.path.insert(0, utils_dir)

try:
    from trading_utils import is_market_open, APIClient
    from optionchain_utils import (
        OptionChainClient,
        OptionPositionTracker,
        choose_monthly_expiry,
        is_chain_valid,
        safe_float,
        safe_int,
    )
    from strategy_common import SignalDebouncer, TradeLimiter, format_kv
except ImportError:
    print("ERROR: Could not import strategy utilities.", flush=True)
    sys.exit(1)


class PrintLogger:
    def info(self, msg): print(msg, flush=True)
    def warning(self, msg): print(msg, flush=True)
    def error(self, msg, exc_info=False): print(msg, flush=True)
    def debug(self, msg): print(msg, flush=True)


# Configuration
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "BankNiftyHDFCCorrelation")
UNDERLYING = os.getenv("UNDERLYING", "BANKNIFTY")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "NSE")
PRODUCT = os.getenv("PRODUCT", "MIS")
QUANTITY = safe_int(os.getenv("QUANTITY", "15")) # 1 Lot

# Strategy Parameters
HDFC_THRESHOLD = safe_float(os.getenv("HDFC_THRESHOLD", "1.0")) # 1%
ICICI_THRESHOLD = safe_float(os.getenv("ICICI_THRESHOLD", "0.5")) # 0.5%
SL_PCT = safe_float(os.getenv("SL_PCT", "20.0"))
TP_PCT = safe_float(os.getenv("TP_PCT", "40.0"))
MAX_HOLD_MIN = safe_int(os.getenv("MAX_HOLD_MIN", "120")) # 2 Hours
MAX_ORDERS_PER_DAY = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "1"))

# Time Filters
ENTRY_START_TIME = os.getenv("ENTRY_START_TIME", "09:30")
ENTRY_END_TIME = os.getenv("ENTRY_END_TIME", "14:30")
EXIT_TIME = os.getenv("EXIT_TIME", "15:15")

API_KEY = os.getenv("OPENALGO_APIKEY")
HOST = os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000")

# Root dir for DB access if needed
root_dir = os.path.dirname(strategies_dir)
sys.path.insert(0, root_dir)

if not API_KEY:
    try:
        from database.auth_db import get_first_available_api_key
        API_KEY = get_first_available_api_key()
    except Exception:
        pass

if not API_KEY:
    raise ValueError("API Key must be set in OPENALGO_APIKEY environment variable")


class BankNiftyHDFCCorrelation:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)

        self.tracker = OptionPositionTracker(
            sl_pct=SL_PCT,
            tp_pct=TP_PCT,
            max_hold_min=MAX_HOLD_MIN
        )
        self.limiter = TradeLimiter(
            max_per_day=MAX_ORDERS_PER_DAY,
            max_per_hour=MAX_ORDERS_PER_DAY, # Same as daily
            cooldown_seconds=300
        )
        self.debouncer = SignalDebouncer()

        self.expiry = None
        self.last_expiry_check = 0

        self.logger.info(f"Strategy Initialized: {STRATEGY_NAME}")
        self.logger.info(format_kv(
            hdfc_threshold=HDFC_THRESHOLD,
            icici_threshold=ICICI_THRESHOLD,
            sl_pct=SL_PCT,
            tp_pct=TP_PCT
        ))

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_check > 3600):
            try:
                res = self.client.expiry(UNDERLYING, OPTIONS_EXCHANGE, "options")
                if res.get("status") == "success":
                    dates = res.get("data", [])
                    if dates:
                        self.expiry = choose_monthly_expiry(dates)
                        self.last_expiry_check = now
                        self.logger.info(f"Selected Monthly Expiry: {self.expiry}")
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

    def get_change_percent(self, symbol):
        """Fetches quote and calculates change percent."""
        try:
            # Assuming NSE for component stocks
            quote = self.api_client.get_quote(symbol, "NSE")
            if not quote:
                return None

            ltp = safe_float(quote.get("ltp"))
            close = safe_float(quote.get("ohlc", {}).get("close"))

            if close == 0:
                return 0.0

            change = ((ltp - close) / close) * 100
            return change
        except Exception as e:
            self.logger.error(f"Error getting quote for {symbol}: {e}")
            return None

    def get_atm_call(self, chain):
        """Finds ATM Call leg details."""
        for item in chain:
            if item.get("ce", {}).get("label") == "ATM":
                ce = item["ce"]
                return {
                    "symbol": ce.get("symbol"),
                    "ltp": safe_float(ce.get("ltp")),
                    "action": "BUY",
                    "quantity": QUANTITY,
                    "product": PRODUCT
                }
        return None

    def _close_position(self, chain, reason):
        self.logger.info(f"Closing position. Reason: {reason}")

        for leg in self.tracker.open_legs:
            try:
                # We are Long Calls, so we SELL to close
                res = self.api_client.placesmartorder(
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
        self.logger.info("Starting Correlation Strategy Loop...")

        while True:
            try:
                if not is_market_open():
                    time.sleep(20)
                    continue

                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(10)
                    continue

                # 1. Manage Existing Position
                if self.tracker.open_legs:
                    # Fetch chain for PnL tracking
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

                # 2. Check Signals (Only if no position)
                if self.is_time_window_open() and self.limiter.allow():

                    hdfc_chg = self.get_change_percent("HDFCBANK")
                    icici_chg = self.get_change_percent("ICICIBANK")

                    if hdfc_chg is not None and icici_chg is not None:
                        self.logger.info(f"Monitor: HDFCBANK={hdfc_chg:.2f}% ICICIBANK={icici_chg:.2f}%")

                        condition = (hdfc_chg >= HDFC_THRESHOLD) and (icici_chg >= ICICI_THRESHOLD)

                        if self.debouncer.edge("BULLISH_SIGNAL", condition):
                            self.logger.info("Bullish Signal Detected! Placing Order...")

                            # Fetch Chain to get ATM
                            chain_resp = self.client.optionchain(
                                underlying=UNDERLYING,
                                exchange=UNDERLYING_EXCHANGE,
                                expiry_date=self.expiry,
                                strike_count=6
                            )
                            chain = chain_resp.get("chain", [])

                            atm_leg = self.get_atm_call(chain)

                            if atm_leg:
                                try:
                                    res = self.api_client.placesmartorder(
                                        strategy=STRATEGY_NAME,
                                        symbol=atm_leg["symbol"],
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

                                        # Track position
                                        self.tracker.add_legs(
                                            legs=[atm_leg],
                                            entry_prices=[atm_leg["ltp"]],
                                            side="BUY"
                                        )
                                    else:
                                        self.logger.error(f"Order Failed: {res.get('message')}")
                                except Exception as e:
                                    self.logger.error(f"Execution Error: {e}")
                            else:
                                self.logger.warning("Could not find ATM Call.")

                    time.sleep(5)
                else:
                    time.sleep(10)

            except Exception as e:
                self.logger.error(f"Loop Error: {e}")
                time.sleep(10)

if __name__ == "__main__":
    try:
        s = BankNiftyHDFCCorrelation()
        s.run()
    except KeyboardInterrupt:
        pass
