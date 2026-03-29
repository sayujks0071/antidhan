#!/usr/bin/env python3
"""
Best Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Iron Condor entering after 10 AM with straddle premium > 120, max hold 45m.
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
sys.path.insert(0, utils_dir)

try:
    from trading_utils import is_market_open, APIClient
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


class PrintLogger:
    def info(self, msg): print(msg, flush=True)
    def warning(self, msg): print(msg, flush=True)
    def error(self, msg, exc_info=False): print(msg, flush=True)
    def debug(self, msg): print(msg, flush=True)


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


class StrategyClass:
    def __init__(self):
        self.logger = PrintLogger()
        self.strategy_name = os.getenv("STRATEGY_NAME", "BestNiftyIronCondor")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = safe_int(os.getenv("QUANTITY", "1"), 1)
        self.strike_count = safe_int(os.getenv("STRIKE_COUNT", "12"), 12)

        self.sl_pct = safe_float(os.getenv("SL_PCT", "40.0"), 40.0)
        self.tp_pct = safe_float(os.getenv("TP_PCT", "50.0"), 50.0)
        self.max_hold_min = safe_int(os.getenv("MAX_HOLD_MIN", "45"), 45)

        self.sleep_seconds = safe_int(os.getenv("SLEEP_SECONDS", "30"), 30)
        self.cooldown_seconds = safe_int(os.getenv("COOLDOWN_SECONDS", "300"), 300)
        self.expiry_refresh_sec = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "3600"), 3600)

        self.max_orders_per_day = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "1"), 1)
        self.max_orders_per_hour = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "1"), 1)

        self.min_straddle_premium = safe_float(os.getenv("MIN_STRADDLE_PREMIUM", "120.0"), 120.0)

        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)
        self.tracker = OptionPositionTracker(sl_pct=self.sl_pct, tp_pct=self.tp_pct, max_hold_min=self.max_hold_min)
        self.limiter = TradeLimiter(max_per_day=self.max_orders_per_day, max_per_hour=self.max_orders_per_hour, cooldown_seconds=self.cooldown_seconds)
        self.debouncer = SignalDebouncer()

        self.manual_expiry = os.getenv("EXPIRY_DATE", "")
        self.expiry = None
        self.last_expiry_fetch = 0

        self.entered_today = False
        self.last_trade_date = None
        self.all_open_legs = []

    def ensure_expiry(self):
        now = time.time()
        if self.manual_expiry:
            self.expiry = self.manual_expiry
            return

        if not self.expiry or (now - self.last_expiry_fetch) > self.expiry_refresh_sec:
            try:
                res = self.client.expiry(self.underlying, self.options_exchange, "options")
                if res and res.get("status") == "success" and res.get("data"):
                    dates = res.get("data")
                    nearest = choose_nearest_expiry(dates)
                    if nearest:
                        self.expiry = nearest
                        self.last_expiry_fetch = now
                        self.logger.info(format_kv(msg="Resolved nearest expiry", expiry=self.expiry))
            except Exception as e:
                self.logger.error(f"Error fetching expiry: {e}")

    def _get_option_data(self, chain, label, opt_type):
        for item in chain:
            opt = item.get(opt_type.lower(), {})
            if opt.get("label") == label:
                return opt, item.get("strike")
        return None, None

    def _close_position(self, chain, reason):
        self.logger.info(f"event=trade action=CLOSE reason={reason}")
        if not self.all_open_legs:
            self.tracker.clear()
            return

        # Close each leg explicitly using APIClient to avoid OptionPositionTracker offset drift issues
        for leg in self.all_open_legs:
            try:
                symbol = leg.get("symbol")
                action = "BUY" if leg.get("action") == "SELL" else "SELL"
                if symbol:
                    resp = self.api_client.placesmartorder(
                        strategy=self.strategy_name,
                        symbol=symbol,
                        action=action,
                        exchange=self.options_exchange,
                        pricetype="MARKET",
                        product=self.product,
                        quantity=self.quantity,
                        position_size=0
                    )
                    self.logger.info(f"Trade response for closing {symbol}: {resp}")
            except Exception as e:
                self.logger.error(f"Error closing leg {leg}: {e}")

        self.tracker.clear()
        self.all_open_legs = []

    def can_trade(self):
        now = datetime.now()

        if self.last_trade_date != now.date():
            self.entered_today = False
            self.last_trade_date = now.date()

        if self.entered_today:
            return False

        current_time = now.time()

        # Enter after 10 AM, Exit by 3:15 PM
        if current_time < datetime.strptime("10:00", "%H:%M").time():
            return False

        if current_time >= datetime.strptime("15:15", "%H:%M").time():
            return False

        return self.limiter.allow()

    def run(self):
        self.logger.info(f"Starting {self.strategy_name}...")

        while True:
            try:
                now = datetime.now()

                if not is_market_open():
                    time.sleep(self.sleep_seconds)
                    continue

                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(self.sleep_seconds)
                    continue

                chain_resp = self.client.optionchain(
                    underlying=self.underlying,
                    exchange=self.underlying_exchange,
                    expiry_date=self.expiry,
                    strike_count=self.strike_count
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=10, require_oi=False, require_volume=False)
                if not valid:
                    self.logger.warning(f"Invalid chain: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])
                underlying_ltp = safe_float(chain_resp.get("underlying_ltp"))

                # Check 3:15 PM EOD square off
                eod_time = datetime.strptime("15:15", "%H:%M").time()
                is_eod = now.time() >= eod_time

                if self.tracker.open_legs and is_eod:
                    self._close_position(chain, "EOD_Squareoff")
                    time.sleep(self.sleep_seconds)
                    continue

                # EXIT MANAGEMENT FIRST
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                if is_eod:
                    time.sleep(self.sleep_seconds)
                    continue

                # CALCULATE INDICATORS
                atm_ce, _ = self._get_option_data(chain, "ATM", "CE")
                atm_pe, _ = self._get_option_data(chain, "ATM", "PE")

                straddle_premium = 0.0
                if atm_ce and atm_pe:
                    straddle_premium = safe_float(atm_ce.get("ltp")) + safe_float(atm_pe.get("ltp"))

                # ENTRY LOGIC
                condition = straddle_premium > self.min_straddle_premium

                if not self.tracker.open_legs and condition and self.can_trade():
                    # Iron Condor: Buy OTM4 CE/PE, Sell OTM2 CE/PE
                    legs = [
                        {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                        {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                        {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                        {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                    ]

                    self.logger.info(format_kv(
                        event="trade",
                        action="ENTRY",
                        spot=underlying_ltp,
                        straddle_premium=straddle_premium,
                        msg="Placing Iron Condor order"
                    ))

                    response = self.client.optionsmultiorder(
                        strategy=self.strategy_name,
                        underlying=self.underlying,
                        exchange=self.options_exchange,
                        expiry_date=self.expiry,
                        legs=legs
                    )

                    self.logger.info(f"Trade response: {response}")

                    if response and response.get("status") == "success":
                        self.entered_today = True
                        self.limiter.record()

                        tracked_legs = []
                        all_legs = []

                        for leg_def in legs:
                            opt_data, _ = self._get_option_data(chain, leg_def["offset"], leg_def["option_type"])
                            if opt_data:
                                leg_info = {
                                    "symbol": opt_data.get("symbol"),
                                    "action": leg_def["action"],
                                    "entry_price": safe_float(opt_data.get("ltp")),
                                    "quantity": leg_def["quantity"]
                                }
                                all_legs.append(leg_info)

                                if leg_def["action"] == "SELL":
                                    tracked_legs.append(leg_def)

                        self.all_open_legs = all_legs

                        entry_prices = [leg["entry_price"] for leg in all_legs if leg["action"] == "SELL"]
                        if entry_prices:
                            self.tracker.add_legs(tracked_legs, entry_prices, side="SELL")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    StrategyClass().run()
