#!/usr/bin/env python3
"""
Best Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters Iron Condor after 10 AM if straddle premium > 120, using OTM2/OTM4 legs.
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

class StrategyClass:
    def __init__(self):
        self.logger = PrintLogger()
        self.strategy_name = os.getenv("STRATEGY_NAME", "Nifty_Iron_Condor_10AM")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")

        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = int(os.getenv("QUANTITY", "1"))
        self.strike_count = int(os.getenv("STRIKE_COUNT", "12"))

        self.sl_pct = float(os.getenv("SL_PCT", "40"))
        self.tp_pct = float(os.getenv("TP_PCT", "50"))
        self.max_hold_min = int(os.getenv("MAX_HOLD_MIN", "45"))

        self.cooldown_seconds = int(os.getenv("COOLDOWN_SECONDS", "120"))
        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "15"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))

        self.max_orders_per_day = int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
        self.max_orders_per_hour = int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

        self.min_straddle_premium = float(os.getenv("MIN_STRADDLE_PREMIUM", "120"))

        # Utilities
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)
        self.tracker = OptionPositionTracker(sl_pct=self.sl_pct, tp_pct=self.tp_pct, max_hold_min=self.max_hold_min)
        self.limiter = TradeLimiter(max_per_day=self.max_orders_per_day, max_per_hour=self.max_orders_per_hour, cooldown_seconds=self.cooldown_seconds)
        self.debouncer = SignalDebouncer()

        self.expiry = None
        self.last_expiry_refresh = 0
        self.all_open_legs = []
        self.entered_today = False
        self.last_trade_date = None

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_refresh > self.expiry_refresh_sec):
            try:
                res = self.client.expiry(self.underlying, self.options_exchange, "options")
                if res and res.get("status") == "success" and res.get("data"):
                    self.expiry = choose_nearest_expiry(res["data"])
                    self.last_expiry_refresh = now
                    self.logger.info(f"Resolved nearest expiry: {self.expiry}")
            except Exception as e:
                self.logger.error(f"Failed to fetch expiry dates: {e}")

    def can_trade_time(self):
        now = datetime.now()
        # Reset entered_today flag on a new day
        if self.last_trade_date != now.date():
            self.entered_today = False
            self.last_trade_date = now.date()

        # Between 10:00 AM and 3:00 PM
        if now.hour < 10:
            return False
        if now.hour > 14: # after 2:59 PM is too late, exit at 3:15
            return False
        if now.hour == 14 and now.minute > 30: # Don't enter after 2:30 PM
            return False

        return True

    def should_eod_exit(self):
        now = datetime.now()
        if now.hour == 15 and now.minute >= 15:
            return True
        return False

    def get_straddle_premium(self, chain):
        atm_strike = None
        ce_ltp = 0
        pe_ltp = 0

        for item in chain:
            ce = item.get("ce", {})
            if ce.get("label") == "ATM":
                atm_strike = item.get("strike")
                ce_ltp = safe_float(ce.get("ltp", 0))
                break

        if atm_strike:
            for item in chain:
                pe = item.get("pe", {})
                if item.get("strike") == atm_strike and pe.get("label") == "ATM":
                    pe_ltp = safe_float(pe.get("ltp", 0))
                    break

        return ce_ltp + pe_ltp

    def _close_position(self, chain, reason):
        self.logger.info(f"event=trade Closing position. Reason: {reason}")

        # Sort legs to close shorts first (BUY actions) then longs (SELL actions)
        close_legs = []
        for leg in self.all_open_legs:
            # Reverse action
            close_action = "BUY" if leg["action"] == "SELL" else "SELL"
            close_legs.append({
                "symbol": leg["symbol"],
                "action": close_action,
                "quantity": leg["quantity"]
            })

        close_legs.sort(key=lambda x: 0 if x["action"] == "BUY" else 1)

        for leg in close_legs:
            try:
                resp = self.api_client.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=leg["symbol"],
                    action=leg["action"],
                    exchange=self.options_exchange,
                    pricetype="MARKET",
                    product=self.product,
                    quantity=leg["quantity"],
                    position_size=0 # Set to 0 to close
                )
                self.logger.info(f"Trade response (Close): {resp}")
            except Exception as e:
                self.logger.error(f"Failed to close leg {leg['symbol']}: {e}")

        self.tracker.clear()
        self.all_open_legs = []
        self.logger.info("Position fully closed.")

    def run(self):
        self.logger.info(f"Starting Nifty Iron Condor strategy for {self.underlying}")
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

                valid, reason = is_chain_valid(chain_resp, min_strikes=8)
                if not valid:
                    self.logger.debug(f"Invalid chain: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])
                underlying_ltp = chain_resp.get("underlying_ltp", 0)

                # EXIT MANAGEMENT FIRST
                if self.tracker.open_legs:
                    # Check EOD Exit
                    if self.should_eod_exit():
                        self._close_position(chain, "EOD_Square_off")
                        time.sleep(self.sleep_seconds)
                        continue

                    # Check Tracker Exits (SL/TP/Time)
                    exit_now, _, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                    # If position open and no exit condition met, just sleep
                    self.logger.debug(format_kv(spot=underlying_ltp, status="Holding_Condor"))

                # ENTRY LOGIC
                if not self.tracker.open_legs and not self.entered_today and self.can_trade_time():
                    if not self.limiter.allow():
                        time.sleep(self.sleep_seconds)
                        continue

                    straddle_premium = self.get_straddle_premium(chain)

                    if straddle_premium > self.min_straddle_premium:
                        # Find OTM2 and OTM4 legs
                        sell_ce = None
                        sell_pe = None
                        buy_ce = None
                        buy_pe = None

                        for item in chain:
                            ce = item.get("ce", {})
                            pe = item.get("pe", {})

                            if ce.get("label") == "OTM2": sell_ce = ce
                            if ce.get("label") == "OTM4": buy_ce = ce
                            if pe.get("label") == "OTM2": sell_pe = pe
                            if pe.get("label") == "OTM4": buy_pe = pe

                        if sell_ce and sell_pe and buy_ce and buy_pe:
                            self.logger.info(format_kv(spot=underlying_ltp, premium=straddle_premium, signal="ENTRY_IRON_CONDOR"))

                            # Place multi-leg order
                            # BUY legs first for margin
                            legs = [
                                {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                                {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                                {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                                {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                            ]

                            resp = self.client.optionsmultiorder(
                                strategy=self.strategy_name,
                                underlying=self.underlying,
                                exchange=self.underlying_exchange,
                                expiry_date=self.expiry,
                                legs=legs
                            )

                            self.logger.info(f"Trade response (Entry): {resp}")

                            # Add to tracker (only short legs for risk management as per memory)
                            tracker_legs = [
                                {"symbol": sell_ce["symbol"], "action": "SELL", "quantity": self.quantity},
                                {"symbol": sell_pe["symbol"], "action": "SELL", "quantity": self.quantity}
                            ]

                            self.tracker.add_legs(
                                tracker_legs,
                                [safe_float(sell_ce["ltp"]), safe_float(sell_pe["ltp"])],
                                side="SELL"
                            )

                            # Keep track of all legs for exiting
                            self.all_open_legs = [
                                {"symbol": buy_ce["symbol"], "action": "BUY", "quantity": self.quantity},
                                {"symbol": buy_pe["symbol"], "action": "BUY", "quantity": self.quantity},
                                {"symbol": sell_ce["symbol"], "action": "SELL", "quantity": self.quantity},
                                {"symbol": sell_pe["symbol"], "action": "SELL", "quantity": self.quantity}
                            ]

                            self.entered_today = True
                            self.limiter.record()

            except Exception as e:
                self.logger.error(f"Error: {e}")

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    StrategyClass().run()
