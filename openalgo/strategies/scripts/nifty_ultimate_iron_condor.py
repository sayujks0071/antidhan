#!/usr/bin/env python3
"""
Nifty Premium Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters after 10 AM when straddle premium > 120. Sells OTM2 CE/PE, buys OTM4 CE/PE.
"""
import os
import sys
import time
from datetime import datetime

# Line-buffered output (required for real-time log capture)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)

# Path setup for utility imports
script_dir = os.path.dirname(os.path.abspath(__file__))
strategies_dir = os.path.dirname(script_dir)
utils_dir = os.path.join(strategies_dir, "utils")
root_dir = os.path.dirname(strategies_dir)
sys.path.insert(0, root_dir)
sys.path.insert(0, utils_dir)

try:
    from trading_utils import is_market_open, APIClient
    from optionchain_utils import (
        OptionChainClient,
        OptionPositionTracker,
        choose_nearest_expiry,
        is_chain_valid,
        normalize_expiry,
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


# Configuration Section
API_KEY = os.getenv("OPENALGO_APIKEY")
HOST = os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000")

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

STRATEGY_NAME = os.getenv("STRATEGY_NAME", "NiftyPremiumIC")
UNDERLYING = os.getenv("UNDERLYING", "NIFTY")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "NFO")
PRODUCT = os.getenv("PRODUCT", "MIS")
QUANTITY = int(os.getenv("QUANTITY", "1"))
STRIKE_COUNT = int(os.getenv("STRIKE_COUNT", "12"))

# Strategy Parameters
MIN_PREMIUM = float(os.getenv("MIN_PREMIUM", "120.0"))
SL_PCT = float(os.getenv("SL_PCT", "40.0"))
TP_PCT = float(os.getenv("TP_PCT", "50.0"))
MAX_HOLD_MIN = int(os.getenv("MAX_HOLD_MIN", "45"))

COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "120"))
SLEEP_SECONDS = int(os.getenv("SLEEP_SECONDS", "30"))
EXPIRY_REFRESH_SEC = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))

MAX_ORDERS_PER_DAY = int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
MAX_ORDERS_PER_HOUR = int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

class NiftyIronCondorStrategy:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)
        self.tracker = OptionPositionTracker(sl_pct=SL_PCT, tp_pct=TP_PCT, max_hold_min=MAX_HOLD_MIN)
        self.limiter = TradeLimiter(
            max_per_day=MAX_ORDERS_PER_DAY,
            max_per_hour=MAX_ORDERS_PER_HOUR,
            cooldown_seconds=COOLDOWN_SECONDS
        )
        self.debouncer = SignalDebouncer()

        self.expiry = None
        self.last_expiry_check = 0

        # State tracking for daily entry
        self.entered_today = False
        self.current_date = datetime.now().date()
        self.all_open_legs = [] # keep track of all legs for exiting

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_check > EXPIRY_REFRESH_SEC):
            try:
                res = self.client.expiry(UNDERLYING, OPTIONS_EXCHANGE, "options")
                if res and res.get("status") == "success" and res.get("data"):
                    dates = res.get("data", [])
                    self.expiry = choose_nearest_expiry(dates)
                    self.last_expiry_check = now
                    self.logger.info(f"Resolved expiry: {self.expiry}")
            except Exception as e:
                self.logger.error(f"Error fetching expiry: {e}")

    def get_atm_straddle_premium(self, chain):
        for item in chain:
            if item.get("ce", {}).get("label") == "ATM" and item.get("pe", {}).get("label") == "ATM":
                ce_ltp = safe_float(item.get("ce", {}).get("ltp"))
                pe_ltp = safe_float(item.get("pe", {}).get("ltp"))
                if ce_ltp > 0 and pe_ltp > 0:
                    return ce_ltp + pe_ltp
        return 0.0

    def can_trade_now(self):
        now = datetime.now()

        # Reset daily flags if new day
        if now.date() != self.current_date:
            self.current_date = now.date()
            self.entered_today = False

        if self.entered_today:
            return False

        # 10:00 AM to 2:30 PM entry window
        start_time = now.replace(hour=10, minute=0, second=0, microsecond=0)
        end_time = now.replace(hour=14, minute=30, second=0, microsecond=0)

        return start_time <= now <= end_time

    def is_eod_square_off_time(self):
        now = datetime.now()
        # Square off by 3:15 PM
        end_time = now.replace(hour=15, minute=15, second=0, microsecond=0)
        return now >= end_time

    def _close_position(self, reason):
        self.logger.info(format_kv(event="close_position", reason=reason, legs=len(self.all_open_legs)))

        for leg in self.all_open_legs:
            # reverse action
            close_action = "BUY" if leg.get("action") == "SELL" else "SELL"
            symbol = leg.get("symbol")

            try:
                self.logger.info(f"Closing leg {symbol} with {close_action}")
                resp = self.api_client.placesmartorder(
                    strategy=STRATEGY_NAME,
                    symbol=symbol,
                    action=close_action,
                    exchange=OPTIONS_EXCHANGE,
                    pricetype="MARKET",
                    product=PRODUCT,
                    quantity=QUANTITY,
                    position_size=0 # Set to 0 to close
                )
                self.logger.info(format_kv(event="trade", symbol=symbol, action=close_action, status=resp.get("status")))
            except Exception as e:
                self.logger.error(f"Failed to close leg {symbol}: {e}")

        self.tracker.clear()
        self.all_open_legs = []

    def extract_entry_prices(self, legs, chain):
        entry_prices = []
        for leg in legs:
            offset = leg.get("offset")
            opt_type = leg.get("option_type").lower()

            # Find the price in chain
            found = False
            for item in chain:
                if item.get(opt_type, {}).get("label") == offset:
                    entry_prices.append(safe_float(item.get(opt_type, {}).get("ltp")))
                    found = True
                    break
            if not found:
                 entry_prices.append(0.0)
        return entry_prices

    def get_symbol_for_offset(self, chain, offset, opt_type):
        opt_type = opt_type.lower()
        for item in chain:
            if item.get(opt_type, {}).get("label") == offset:
                return item.get(opt_type, {}).get("symbol")
        return None

    def run(self):
        self.logger.info(f"Starting {STRATEGY_NAME} strategy loop...")

        while True:
            try:
                if not is_market_open():
                    time.sleep(SLEEP_SECONDS)
                    continue

                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(SLEEP_SECONDS)
                    continue

                # EOD Exit Check
                if self.is_eod_square_off_time() and self.all_open_legs:
                     self._close_position("EOD_Squareoff")
                     time.sleep(SLEEP_SECONDS)
                     continue

                chain_resp = self.client.optionchain(
                    underlying=UNDERLYING,
                    exchange=UNDERLYING_EXCHANGE,
                    expiry_date=self.expiry,
                    strike_count=STRIKE_COUNT
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=8)
                if not valid:
                    self.logger.warning(f"Invalid chain: {reason}")
                    time.sleep(SLEEP_SECONDS)
                    continue

                chain = chain_resp.get("chain", [])
                spot = chain_resp.get("underlying_ltp", 0.0)

                # EXIT MANAGEMENT
                if self.tracker.open_legs:
                    exit_now, exit_legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(exit_reason)
                        time.sleep(SLEEP_SECONDS)
                        continue

                # ENTRY LOGIC
                if not self.tracker.open_legs and self.can_trade_now() and self.limiter.allow():
                    straddle_premium = self.get_atm_straddle_premium(chain)

                    self.logger.info(format_kv(spot=spot, premium=straddle_premium, min_required=MIN_PREMIUM))

                    # Entry condition
                    condition_met = straddle_premium > MIN_PREMIUM

                    # Debounce signal
                    signal = self.debouncer.edge("entry_signal", condition_met)

                    if signal:
                        self.logger.info(format_kv(event="signal", message="Premium > 120 and > 10 AM, entering Iron Condor"))

                        legs_to_execute = [
                            {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": QUANTITY, "product": PRODUCT},
                            {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": QUANTITY, "product": PRODUCT},
                            {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": QUANTITY, "product": PRODUCT},
                            {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": QUANTITY, "product": PRODUCT},
                        ]

                        response = self.client.optionsmultiorder(
                            strategy=STRATEGY_NAME,
                            underlying=UNDERLYING,
                            exchange=UNDERLYING_EXCHANGE,
                            expiry_date=self.expiry,
                            legs=legs_to_execute
                        )

                        if response and response.get("status") == "success":
                            self.logger.info(format_kv(event="trade", status="success", message="Iron Condor entered"))
                            self.limiter.record()
                            self.entered_today = True

                            # We only track short legs for SL/TP in OptionPositionTracker to avoid false exits
                            short_legs = [leg for leg in legs_to_execute if leg["action"] == "SELL"]
                            short_entry_prices = self.extract_entry_prices(short_legs, chain)

                            # Add strictly short legs to tracker
                            self.tracker.add_legs(short_legs, short_entry_prices, side="SELL")

                            # Store ALL legs for full position closing
                            for leg in legs_to_execute:
                                symbol = self.get_symbol_for_offset(chain, leg["offset"], leg["option_type"])
                                if symbol:
                                    leg_copy = leg.copy()
                                    leg_copy["symbol"] = symbol
                                    self.all_open_legs.append(leg_copy)

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    strategy = NiftyIronCondorStrategy()
    strategy.run()
