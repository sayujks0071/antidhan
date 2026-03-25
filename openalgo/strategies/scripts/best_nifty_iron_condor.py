#!/usr/bin/env python3
"""
Best Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters Iron Condor after 10 AM if straddle premium > 120. Sells OTM2, Buys OTM4. Max hold 45 mins.
"""
import os
import sys
import time
from datetime import datetime, time as datetime_time

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
    from trading_utils import is_market_open
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


class BestNiftyIronCondor:
    def __init__(self):
        self.logger = PrintLogger()
        self.strategy_name = os.getenv("STRATEGY_NAME", "best_nifty_iron_condor")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")

        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = safe_int(os.getenv("QUANTITY", "1"), 1)
        self.strike_count = safe_int(os.getenv("STRIKE_COUNT", "10"), 10)

        # Risk Parameters
        self.sl_pct = safe_float(os.getenv("SL_PCT", "40.0"), 40.0)
        self.tp_pct = safe_float(os.getenv("TP_PCT", "50.0"), 50.0)
        self.max_hold_min = safe_int(os.getenv("MAX_HOLD_MIN", "45"), 45)

        self.cooldown_seconds = safe_int(os.getenv("COOLDOWN_SECONDS", "120"), 120)
        self.sleep_seconds = safe_int(os.getenv("SLEEP_SECONDS", "15"), 15)
        self.expiry_refresh_sec = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "3600"), 3600)

        self.max_orders_per_day = safe_int(os.getenv("MAX_ORDERS_PER_DAY", "1"), 1)
        self.max_orders_per_hour = safe_int(os.getenv("MAX_ORDERS_PER_HOUR", "1"), 1)

        # Strategy Constraints
        self.min_premium = safe_float(os.getenv("MIN_PREMIUM", "120.0"), 120.0)
        self.sell_offset = "OTM2"
        self.buy_offset = "OTM4"

        # Initialization
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.tracker = OptionPositionTracker(
            sl_pct=self.sl_pct,
            tp_pct=self.tp_pct,
            max_hold_min=self.max_hold_min
        )
        self.limiter = TradeLimiter(
            max_per_day=self.max_orders_per_day,
            max_per_hour=self.max_orders_per_hour,
            cooldown_seconds=self.cooldown_seconds
        )
        self.debouncer = SignalDebouncer()

        self.expiry = os.getenv("EXPIRY_DATE", None)
        self.last_expiry_check = 0
        self.entered_today = False
        self.all_open_legs = []

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_check) > self.expiry_refresh_sec:
            try:
                res = self.client.expiry(self.underlying, self.options_exchange, "options")
                if res and res.get("status") == "success" and res.get("data"):
                    dates = res.get("data")
                    self.expiry = choose_nearest_expiry(dates)
                    self.last_expiry_check = now
                    self.logger.info(f"Resolved nearest expiry: {self.expiry}")
            except Exception as e:
                self.logger.error(f"Failed to fetch expiry: {e}")

    def _get_option_by_label(self, chain, label, option_type):
        """Helper to find option data by label (e.g., 'OTM2', 'ATM')."""
        for item in chain:
            opt = item.get(option_type.lower())
            if opt and opt.get("label") == label:
                return opt
        return None

    def can_trade_time(self):
        """Check if current time is within trading window (10:00 AM to 3:15 PM)."""
        now = datetime.now().time()
        start_time = datetime_time(10, 0)
        end_time = datetime_time(15, 15)
        return start_time <= now < end_time

    def check_eod_exit(self):
        """Force exit if time is past 3:15 PM."""
        now = datetime.now().time()
        return now >= datetime_time(15, 15)

    def close_all_legs(self, reason):
        """Close all legs directly using standard APIClient."""
        from trading_utils import APIClient
        api = APIClient(api_key=API_KEY, host=HOST)

        self.logger.info(f"event=exit reason={reason} Closing all positions.")
        for leg in self.all_open_legs:
            try:
                close_action = "BUY" if leg["action"] == "SELL" else "SELL"
                resp = api.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=leg["symbol"],
                    action=close_action,
                    exchange=self.options_exchange,
                    pricetype="MARKET",
                    product=self.product,
                    quantity=self.quantity,
                    position_size=0
                )
                self.logger.info(f"Closed leg {leg['symbol']} {close_action}: {resp}")
            except Exception as e:
                self.logger.error(f"Error closing leg {leg['symbol']}: {e}")

        self.tracker.clear()
        self.all_open_legs = []

    def get_atm_straddle_premium(self, chain):
        atm_ce = self._get_option_by_label(chain, "ATM", "ce")
        atm_pe = self._get_option_by_label(chain, "ATM", "pe")
        if atm_ce and atm_pe:
            return safe_float(atm_ce.get("ltp")) + safe_float(atm_pe.get("ltp"))
        return 0.0

    def run(self):
        self.logger.info(f"Starting {self.strategy_name} strategy loop.")

        while True:
            try:
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

                valid, reason = is_chain_valid(chain_resp, min_strikes=8, require_oi=False, require_volume=False)
                if not valid:
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])
                spot = chain_resp.get("underlying_ltp")

                # EXIT MANAGEMENT FIRST
                if self.tracker.open_legs:
                    # Check EOD Exit
                    if self.check_eod_exit():
                        self.close_all_legs("EOD_SQUARE_OFF")
                        time.sleep(self.sleep_seconds)
                        continue

                    # Check normal SL/TP/Time limits (only evaluates the short legs tracked)
                    exit_now, exit_legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self.close_all_legs(exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # Check Daily Reset for limiters
                if self.check_eod_exit():
                    self.entered_today = False

                # ENTRY LOGIC
                if not self.tracker.open_legs and self.can_trade_time() and not self.entered_today:
                    straddle_premium = self.get_atm_straddle_premium(chain)

                    self.logger.info(format_kv(spot=spot, straddle_prem=straddle_premium, min_prem=self.min_premium))

                    # Condition: Premium > 120
                    signal_condition = straddle_premium > self.min_premium
                    signal = self.debouncer.edge("enter_ic", signal_condition)

                    if signal and self.limiter.allow():
                        self.logger.info(f"event=trade Signal triggered. Executing Iron Condor.")

                        # Prepare legs (BUY wings first for margin benefit, then SELL body)
                        legs_req = [
                            {"offset": self.buy_offset, "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": self.buy_offset, "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": self.sell_offset, "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                            {"offset": self.sell_offset, "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                        ]

                        try:
                            resp = self.client.optionsmultiorder(
                                strategy=self.strategy_name,
                                underlying=self.underlying,
                                exchange=self.options_exchange,
                                expiry_date=self.expiry,
                                legs=legs_req
                            )
                            self.logger.info(f"Trade response: {resp}")

                            if resp and resp.get("status") == "success":
                                self.limiter.record()
                                self.entered_today = True

                                # Extract specific execution details to track SL/TP on short legs
                                # and track all symbols for closing
                                short_legs_for_tracker = []
                                entry_prices = []
                                self.all_open_legs = []

                                for leg in legs_req:
                                    opt_data = self._get_option_by_label(chain, leg["offset"], leg["option_type"])
                                    if opt_data:
                                        symbol = opt_data.get("symbol")
                                        ltp = safe_float(opt_data.get("ltp"))

                                        leg_info = {"symbol": symbol, "action": leg["action"]}
                                        self.all_open_legs.append(leg_info)

                                        if leg["action"] == "SELL":
                                            tracker_leg = {
                                                "symbol": symbol,
                                                "option_type": leg["option_type"],
                                                "strike": opt_data.get("strike", 0.0),
                                                "action": "SELL"
                                            }
                                            short_legs_for_tracker.append(tracker_leg)
                                            entry_prices.append(ltp)

                                if short_legs_for_tracker:
                                    self.tracker.add_legs(short_legs_for_tracker, entry_prices, side="SELL")
                                    self.logger.info(f"Position opened. Tracking {len(short_legs_for_tracker)} short legs for SL/TP.")

                        except Exception as e:
                            self.logger.error(f"Error placing multi-leg order: {e}")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(self.sleep_seconds)


if __name__ == "__main__":
    BestNiftyIronCondor().run()
