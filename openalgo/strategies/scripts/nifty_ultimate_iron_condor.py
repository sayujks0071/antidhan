#!/usr/bin/env python3
"""
Nifty Ultimate Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters an Iron Condor after 10 AM if straddle premium > 120. Sells OTM2 and Buys OTM4.
Strict 40% SL, 50% TP, and 45-minute max hold. Single trade per day.
"""
import os
import sys
import time
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

# Configuration via os.getenv with sensible defaults
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "Nifty_Ultimate_IC")
UNDERLYING = os.getenv("UNDERLYING", "NIFTY")
UNDERLYING_EXCHANGE = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
OPTIONS_EXCHANGE = os.getenv("OPTIONS_EXCHANGE", "NFO")

PRODUCT = os.getenv("PRODUCT", "MIS")
QUANTITY = safe_int(os.getenv("QUANTITY", "1"))
STRIKE_COUNT = safe_int(os.getenv("STRIKE_COUNT", "12"))

SL_PCT = safe_float(os.getenv("SL_PCT", "40.0"))
TP_PCT = safe_float(os.getenv("TP_PCT", "50.0"))
MAX_HOLD_MIN = safe_int(os.getenv("MAX_HOLD_MIN", "45"))

COOLDOWN_SECONDS = safe_int(os.getenv("COOLDOWN_SECONDS", "120"))
SLEEP_SECONDS = safe_int(os.getenv("SLEEP_SECONDS", "15"))
EXPIRY_REFRESH_SEC = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))

MAX_ORDERS_PER_DAY = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
MAX_ORDERS_PER_HOUR = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

# Strategy specific
MIN_STRADDLE_PREMIUM = safe_float(os.getenv("MIN_STRADDLE_PREMIUM", "120.0"))
ENTRY_TIME_START = os.getenv("ENTRY_TIME_START", "10:00")
ENTRY_TIME_END = os.getenv("ENTRY_TIME_END", "14:30")
EOD_EXIT_TIME = os.getenv("EOD_EXIT_TIME", "15:15")

EXPIRY_DATE = os.getenv("EXPIRY_DATE", "").strip()

class NiftyUltimateIronCondor:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST) # Used for smart orders
        self.tracker = OptionPositionTracker(sl_pct=SL_PCT, tp_pct=TP_PCT, max_hold_min=MAX_HOLD_MIN)
        self.debouncer = SignalDebouncer()
        self.limiter = TradeLimiter(
            max_per_day=MAX_ORDERS_PER_DAY,
            max_per_hour=MAX_ORDERS_PER_HOUR,
            cooldown_seconds=COOLDOWN_SECONDS
        )
        self.expiry = EXPIRY_DATE
        self.last_expiry_check = time.time() if self.expiry else 0

        # State tracking
        self.all_open_legs = []
        self.entered_today = False
        self.current_date = datetime.now().date()

    def ensure_expiry(self):
        # If manual expiry is set and we haven't hit the refresh limit, return
        if self.expiry and (time.time() - self.last_expiry_check < EXPIRY_REFRESH_SEC):
            return

        # If a hardcoded expiry is provided via env var, don't overwrite it
        if EXPIRY_DATE:
            self.expiry = EXPIRY_DATE
            self.last_expiry_check = time.time()
            return

        self.logger.info("Fetching nearest expiry...")
        try:
            res = self.client.expiry(UNDERLYING, OPTIONS_EXCHANGE, "options")
            if res and res.get("status") == "success":
                dates = res.get("data", [])
                nearest = choose_nearest_expiry(dates)
                if nearest:
                    self.expiry = nearest
                    self.last_expiry_check = time.time()
                    self.logger.info(f"Selected Expiry: {self.expiry}")
                else:
                    self.logger.warning("No future expiry found.")
            else:
                self.logger.warning(f"Failed to fetch expiry: {res.get('message', 'unknown error')}")
        except Exception as e:
            self.logger.error(f"Expiry fetch error: {e}")

    def _close_position(self, chain, reason):
        """Close all open legs individually using APIClient.placesmartorder as per memory constraints."""
        self.logger.info(f"Closing position. Reason: {reason}")
        if not self.all_open_legs:
            return

        for leg in self.all_open_legs:
            symbol = leg.get("symbol")
            if not symbol:
                continue

            # Reverse the action to close
            close_action = "BUY" if leg["action"] == "SELL" else "SELL"
            qty = leg.get("quantity", QUANTITY)

            self.logger.info(f"event=trade action={close_action} symbol={symbol} quantity={qty} product={PRODUCT} reason={reason}")

            try:
                res = self.api_client.placesmartorder(
                    strategy=STRATEGY_NAME,
                    symbol=symbol,
                    action=close_action,
                    exchange=OPTIONS_EXCHANGE,
                    pricetype="MARKET",
                    product=PRODUCT,
                    quantity=qty,
                    position_size=0
                )
                self.logger.info(f"Trade response: {res}")
            except Exception as e:
                self.logger.error(f"Error closing leg {symbol}: {e}")

        # Reset state after attempting to close all
        self.tracker.clear()
        self.all_open_legs = []

    def can_trade(self):
        if self.entered_today:
            return False

        ist_offset = timezone(timedelta(hours=5, minutes=30))
        now = datetime.now(ist_offset).time()
        start_time = datetime.strptime(ENTRY_TIME_START, "%H:%M").time()
        end_time = datetime.strptime(ENTRY_TIME_END, "%H:%M").time()

        if not (start_time <= now <= end_time):
            return False

        return self.limiter.allow()

    def run(self):
        self.logger.info(f"Starting {STRATEGY_NAME} for {UNDERLYING} on {OPTIONS_EXCHANGE}")

        while True:
            try:
                # 0. Daily Reset
                now_date = datetime.now().date()
                if now_date != self.current_date:
                    self.entered_today = False
                    self.current_date = now_date
                    # Note: we do not recreate the TradeLimiter here.
                    # We rely on entered_today to restrict to 1 trade per day.

                # 1. Market Hours
                try:
                    market_open = is_market_open()
                except Exception:
                    market_open = True

                if not market_open:
                    time.sleep(SLEEP_SECONDS)
                    continue

                # 2. Expiry Ensure
                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(SLEEP_SECONDS)
                    continue

                # 3. Fetch Chain
                chain_resp = self.client.optionchain(
                    underlying=UNDERLYING,
                    exchange=UNDERLYING_EXCHANGE,
                    expiry_date=self.expiry,
                    strike_count=STRIKE_COUNT,
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=8)
                if not valid:
                    self.logger.warning(f"Chain invalid: {reason}")
                    time.sleep(SLEEP_SECONDS)
                    continue

                chain = chain_resp.get("chain", [])
                underlying_ltp = safe_float(chain_resp.get("underlying_ltp", 0))

                # 4. Exit Management (Always FIRST)
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)

                    # EOD Exit Check
                    ist_offset = timezone(timedelta(hours=5, minutes=30))
                    now_time = datetime.now(ist_offset).time()
                    eod_time = datetime.strptime(EOD_EXIT_TIME, "%H:%M").time()

                    if now_time >= eod_time:
                        exit_now = True
                        exit_reason = "eod_sqoff"

                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(SLEEP_SECONDS)
                        continue

                # 5. Indicator Calculation
                straddle_premium = 0.0
                atm_item = next((item for item in chain if (item.get("ce") or {}).get("label") == "ATM"), None)
                if atm_item:
                    ce_ltp = safe_float((atm_item.get("ce") or {}).get("ltp"))
                    pe_ltp = safe_float((atm_item.get("pe") or {}).get("ltp"))
                    straddle_premium = ce_ltp + pe_ltp

                if not self.tracker.open_legs:
                    self.logger.info(format_kv(
                        spot=f"{underlying_ltp:.2f}",
                        straddle=f"{straddle_premium:.2f}",
                        pos="FLAT"
                    ))
                else:
                    self.logger.info(format_kv(
                        spot=f"{underlying_ltp:.2f}",
                        pos="OPEN"
                    ))

                # 6. Entry Logic
                if not self.tracker.open_legs and self.can_trade():
                    condition_met = straddle_premium > MIN_STRADDLE_PREMIUM

                    if self.debouncer.edge("entry_signal", condition_met):
                        self.logger.info(f"Entry signal triggered! Straddle Premium: {straddle_premium} > {MIN_STRADDLE_PREMIUM}")

                        # Build legs
                        legs_config = [
                            {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": QUANTITY, "product": PRODUCT},
                            {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": QUANTITY, "product": PRODUCT},
                            {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": QUANTITY, "product": PRODUCT},
                            {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": QUANTITY, "product": PRODUCT},
                        ]

                        try:
                            # Send multi-leg order
                            res = self.client.optionsmultiorder(
                                strategy=STRATEGY_NAME,
                                underlying=UNDERLYING,
                                exchange=OPTIONS_EXCHANGE,
                                expiry_date=self.expiry,
                                legs=legs_config
                            )

                            self.logger.info(f"event=trade action=ENTRY response={res}")

                            if res.get("status") == "success":
                                self.entered_today = True
                                self.limiter.record()

                                # Resolve exact symbols for tracking and exiting
                                resolved_legs = []
                                for cfg in legs_config:
                                    otype = cfg["option_type"].lower()
                                    offset = cfg["offset"]

                                    found_item = next((opt for item in chain for k, opt in item.items() if k == otype and isinstance(opt, dict) and opt.get("label") == offset), None)

                                    if found_item:
                                        symbol = found_item.get("symbol")
                                        ltp = safe_float(found_item.get("ltp"))

                                        leg_info = {
                                            "symbol": symbol,
                                            "option_type": cfg["option_type"],
                                            "action": cfg["action"],
                                            "quantity": cfg["quantity"],
                                            "entry_price": ltp,
                                            "product": cfg["product"]
                                        }
                                        resolved_legs.append(leg_info)

                                self.all_open_legs = resolved_legs

                                # Filter to only short legs to add to tracker
                                short_legs = [leg for leg in resolved_legs if leg["action"] == "SELL"]
                                entry_prices = [leg["entry_price"] for leg in short_legs]

                                if short_legs:
                                    self.tracker.add_legs(short_legs, entry_prices, side="SELL")
                                    self.logger.info(f"Position opened and tracked. Short Legs: {[l['symbol'] for l in short_legs]}")
                                else:
                                    self.logger.warning("No short legs found to track!")

                            else:
                                self.logger.error(f"Entry order failed: {res.get('message')}")

                        except Exception as e:
                            self.logger.error(f"Entry execution error: {e}")

            except Exception as e:
                self.logger.error(f"Main loop error: {e}", exc_info=True)

            time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    strategy = NiftyUltimateIronCondor()
    strategy.run()
