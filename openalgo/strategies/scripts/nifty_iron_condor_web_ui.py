#!/usr/bin/env python3
"""
Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters after 10 AM when straddle premium > 120, sells OTM2, buys OTM4 for protection, strict SL/TP.
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
    from strategy_common import SignalDebouncer, TradeLedger, TradeLimiter, format_kv
except ImportError:
    print("ERROR: Could not import strategy utilities.", flush=True)
    sys.exit(1)

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

class NiftyIronCondorStrategy:
    def __init__(self):
        self.logger = PrintLogger()
        self.logger.info("Initializing Nifty Iron Condor Strategy...")

        # Configuration Section
        self.strategy_name = os.getenv("STRATEGY_NAME", "nifty_iron_condor_web_ui")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")

        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = int(os.getenv("QUANTITY", "1"))
        self.strike_count = int(os.getenv("STRIKE_COUNT", "12"))

        # Strategy-specific parameters
        self.min_straddle_premium = float(os.getenv("MIN_STRADDLE_PREMIUM", "120.0"))
        self.sl_pct = float(os.getenv("SL_PCT", "40.0"))
        self.tp_pct = float(os.getenv("TP_PCT", "50.0"))
        self.max_hold_min = int(os.getenv("MAX_HOLD_MIN", "45"))

        self.cooldown_seconds = int(os.getenv("COOLDOWN_SECONDS", "120"))
        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "15"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))

        self.max_orders_per_day = int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
        self.max_orders_per_hour = int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

        self.manual_expiry_date = os.getenv("EXPIRY_DATE", None)
        self.entered_today = False
        self.last_trade_date = None

        # Clients and Utilities
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST) # Used for exiting individual legs
        self.tracker = OptionPositionTracker(sl_pct=self.sl_pct, tp_pct=self.tp_pct, max_hold_min=self.max_hold_min)
        self.limiter = TradeLimiter(max_per_day=self.max_orders_per_day, max_per_hour=self.max_orders_per_hour, cooldown_seconds=self.cooldown_seconds)
        self.debouncer = SignalDebouncer()

        # State
        self.expiry = None
        self.last_expiry_check = 0
        self.all_open_legs = [] # Maintain all executed legs for individual closing

        self.logger.info(f"Configuration: SL={self.sl_pct}%, TP={self.tp_pct}%, MaxHold={self.max_hold_min}m, MinPremium={self.min_straddle_premium}")

    def ensure_expiry(self):
        current_time = time.time()
        if self.expiry and (current_time - self.last_expiry_check) < self.expiry_refresh_sec:
            return

        if self.manual_expiry_date:
            self.expiry = normalize_expiry(self.manual_expiry_date)
            self.last_expiry_check = current_time
            self.logger.info(f"Using manual expiry: {self.expiry}")
            return

        try:
            res = self.client.expiry(self.underlying, self.options_exchange, "options")
            if res and res.get("status") == "success" and res.get("data"):
                expiries = res["data"]
                nearest = choose_nearest_expiry(expiries)
                if nearest != self.expiry:
                    self.expiry = nearest
                    self.logger.info(f"Resolved nearest expiry: {self.expiry}")
                self.last_expiry_check = current_time
            else:
                self.logger.error("Failed to fetch expiries.")
        except Exception as e:
            self.logger.error(f"Error fetching expiry: {e}")

    def get_straddle_premium(self, chain_data, atm_strike):
        """Calculates the premium of the ATM Straddle."""
        for item in chain_data:
            if item.get("strike") == atm_strike:
                ce_ltp = safe_float(item.get("ce", {}).get("ltp"))
                pe_ltp = safe_float(item.get("pe", {}).get("ltp"))
                return ce_ltp + pe_ltp
        return 0.0

    def can_trade_now(self):
        """Checks if current time is within the allowed trading window."""
        now = datetime.now()
        current_time = now.time()

        # Reset daily flag if a new day starts
        current_date = now.date()
        if self.last_trade_date != current_date:
            self.entered_today = False
            self.last_trade_date = current_date

        if self.entered_today:
            return False

        start_time = datetime.strptime("10:00", "%H:%M").time()
        end_time = datetime.strptime("14:30", "%H:%M").time()

        return start_time <= current_time <= end_time

    def should_eod_exit(self):
        """Checks if it's time for EOD square-off (3:15 PM)."""
        now = datetime.now()
        eod_time = datetime.strptime("15:15", "%H:%M").time()
        return now.time() >= eod_time

    def close_all_legs(self, reason):
        """Closes all legs individually using APIClient to avoid spot drift issues."""
        self.logger.info(f"event=trade action=CLOSE_ALL reason={reason} legs={len(self.all_open_legs)}")

        for leg in self.all_open_legs:
            symbol = leg.get("symbol")
            if not symbol:
                continue

            # Reverse the action
            original_action = leg.get("action")
            close_action = "BUY" if original_action == "SELL" else "SELL"

            try:
                self.logger.info(f"Closing leg: {symbol} with {close_action}")
                resp = self.api_client.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=symbol,
                    action=close_action,
                    exchange=self.options_exchange,
                    pricetype="MARKET",
                    product=self.product,
                    quantity=leg.get("quantity", self.quantity),
                    position_size=0
                )
                self.logger.info(f"Trade response: {resp}")
            except Exception as e:
                self.logger.error(f"Error closing leg {symbol}: {e}")

        # Clear tracker and state
        self.tracker.clear()
        self.all_open_legs = []

    def run(self):
        self.logger.info("Strategy started. Waiting for market open...")

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

                valid, reason = is_chain_valid(chain_resp, min_strikes=6, require_oi=False, require_volume=False)
                if not valid:
                    self.logger.warning(f"Invalid chain: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])
                atm_strike = chain_resp.get("atm_strike")
                spot = chain_resp.get("underlying_ltp")

                # EXIT MANAGEMENT FIRST
                if self.tracker.open_legs:
                    # Check Tracker SL/TP/Time
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self.close_all_legs(exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                    # Check EOD
                    if self.should_eod_exit():
                        self.close_all_legs("EOD_square_off")
                        time.sleep(self.sleep_seconds)
                        continue

                # CALCULATE INDICATORS
                straddle_premium = self.get_straddle_premium(chain, atm_strike)

                # Check Entry Signal
                cond_premium = straddle_premium > self.min_straddle_premium
                cond_time = self.can_trade_now()
                cond_no_position = not bool(self.tracker.open_legs)

                signal_cond = cond_premium and cond_time and cond_no_position

                # Use debouncer to prevent rapid re-entries if condition flickers
                if self.debouncer.edge("entry_signal", signal_cond):
                    self.logger.info(format_kv(spot=spot, atm=atm_strike, premium=straddle_premium, signal="ENTRY_DETECTED"))

                    if self.limiter.allow():
                        self.logger.info("Placing Iron Condor order...")

                        # Define legs: Buy OTM4, Sell OTM2
                        # BUY legs execute first for margin efficiency
                        order_legs = [
                            {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                        ]

                        try:
                            response = self.client.optionsmultiorder(
                                strategy=self.strategy_name,
                                underlying=self.underlying,
                                exchange=self.underlying_exchange,
                                expiry_date=self.expiry,
                                legs=order_legs
                            )

                            self.logger.info(f"Trade response: {response}")

                            if response and response.get("status") == "success":
                                # We need to track the exact symbols to close them later
                                executed_legs = response.get("data", [])
                                if executed_legs:
                                    self.all_open_legs = executed_legs

                                    # For SL/TP tracking, we ONLY add the short legs to the tracker
                                    short_legs = [leg for leg in executed_legs if leg.get("action") == "SELL"]

                                    # Create entry prices dictionary from executed prices or chain LTP as fallback
                                    entry_prices = {}
                                    for leg in short_legs:
                                        symbol = leg.get("symbol")
                                        if symbol:
                                            # If API returns price, use it, else try to find it in chain
                                            price = leg.get("price") or leg.get("average_price")
                                            if not price:
                                                for item in chain:
                                                    if item.get("ce", {}).get("symbol") == symbol:
                                                        price = item.get("ce", {}).get("ltp")
                                                    elif item.get("pe", {}).get("symbol") == symbol:
                                                        price = item.get("pe", {}).get("ltp")

                                            entry_prices[symbol] = safe_float(price)

                                    if short_legs:
                                        self.tracker.add_legs(short_legs, entry_prices, side="SELL")
                                        self.limiter.record()
                                        self.entered_today = True
                                        self.logger.info(f"event=trade action=ENTRY status=SUCCESS short_legs={len(short_legs)}")
                                    else:
                                        self.logger.warning("No short legs found in execution response to track.")
                                else:
                                    self.logger.warning("Order successful but no leg data returned to track.")
                            else:
                                self.logger.error("Multi-order failed or returned unexpected response.")

                        except Exception as e:
                            self.logger.error(f"Error placing multi-order: {e}")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    strategy = NiftyIronCondorStrategy()
    strategy.run()
