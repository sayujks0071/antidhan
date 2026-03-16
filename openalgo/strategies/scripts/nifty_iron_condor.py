#!/usr/bin/env python3
"""
NIFTY_IRON_CONDOR - NIFTY Options (OpenAlgo Web UI Compatible)
Iron Condor strategy entering after 10 AM on high straddle premium, 40% SL, 50% TP.
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
        self.logger.info("Initializing NiftyIronCondorStrategy...")

        # Configuration Section
        self.strategy_name = os.getenv("STRATEGY_NAME", "NIFTY_IRON_CONDOR")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = int(os.getenv("QUANTITY", "1"))
        self.strike_count = int(os.getenv("STRIKE_COUNT", "12"))

        # Risk Management Params
        self.sl_pct = float(os.getenv("SL_PCT", "40"))
        self.tp_pct = float(os.getenv("TP_PCT", "50"))
        self.max_hold_min = int(os.getenv("MAX_HOLD_MIN", "45"))

        # Timing Params
        self.cooldown_seconds = int(os.getenv("COOLDOWN_SECONDS", "120"))
        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "30"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))

        # Strategy-specific Params
        self.min_straddle_prem = float(os.getenv("MIN_STRADDLE_PREM", "120"))

        self.max_orders_per_day = int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
        self.max_orders_per_hour = int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

        # Clients and Utilities
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)
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

        # State Variables
        self.expiry = os.getenv("EXPIRY_DATE", None)
        self.last_expiry_refresh = 0
        self.entered_today = False
        self.all_open_legs = []

    def ensure_expiry(self):
        """Fetches and normalizes nearest expiry if not provided or needs refresh."""
        now = time.time()
        if self.expiry and (now - self.last_expiry_refresh) < self.expiry_refresh_sec:
            return

        try:
            res = self.client.expiry(self.underlying, self.options_exchange, "options")
            if res.get("status") == "success":
                dates = res.get("data", [])
                new_expiry = choose_nearest_expiry(dates)
                if new_expiry:
                    self.expiry = new_expiry
                    self.last_expiry_refresh = now
                    self.logger.info(f"Resolved Expiry: {self.expiry}")
            else:
                self.logger.warning(f"Failed to fetch expiry: {res.get('message')}")
        except Exception as e:
            self.logger.error(f"Error fetching expiry: {e}")

    def can_trade_now(self):
        """Validates trading hours (10:00 AM - 2:30 PM)."""
        now = datetime.now()
        # Ensure we haven't entered today
        if self.entered_today:
             return False

        if now.hour < 10 or (now.hour == 14 and now.minute > 30) or now.hour > 14:
             return False

        return True

    def check_eod_squareoff(self):
        """Returns True if it's 3:15 PM or later (15:15)."""
        now = datetime.now()
        if now.hour > 15 or (now.hour == 15 and now.minute >= 15):
             return True
        return False

    def get_straddle_premium(self, chain):
        """Calculates combined ATM CE and PE premium."""
        atm_strike = None
        for item in chain:
            if item.get("ce", {}).get("label") == "ATM":
                atm_strike = item["strike"]
                break

        if not atm_strike:
            return 0.0

        for item in chain:
            if item["strike"] == atm_strike:
                ce_ltp = safe_float(item.get("ce", {}).get("ltp"))
                pe_ltp = safe_float(item.get("pe", {}).get("ltp"))
                return ce_ltp + pe_ltp
        return 0.0

    def _close_position(self, exit_reason):
        """Closes all legs of the active Iron Condor position individually."""
        self.logger.info(f"event=trade action=CLOSE_ALL reason={exit_reason}")
        if not self.all_open_legs:
            return

        for leg in self.all_open_legs:
            symbol = leg.get("symbol")
            action = leg.get("action")

            # Reverse action
            close_action = "BUY" if action.upper() == "SELL" else "SELL"
            qty = leg.get("quantity", self.quantity)

            try:
                resp = self.api_client.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=symbol,
                    action=close_action,
                    exchange=self.options_exchange,
                    pricetype="MARKET",
                    product=self.product,
                    quantity=qty,
                    position_size=0 # Target position size = 0 to close
                )
                self.logger.info(format_kv(
                    event="trade",
                    side=close_action,
                    symbol=symbol,
                    qty=qty,
                    status=resp.get("status", "unknown")
                ))
            except Exception as e:
                self.logger.error(f"Error closing leg {symbol}: {e}")

        # Clear tracker and state
        self.tracker.clear()
        self.all_open_legs = []

    def run(self):
        """Main strategy loop."""
        self.logger.info("Starting NiftyIronCondorStrategy Main Loop...")

        while True:
            try:
                if not is_market_open():
                    time.sleep(self.sleep_seconds)
                    continue

                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(self.sleep_seconds)
                    continue

                # Fetch Option Chain
                chain_resp = self.client.optionchain(
                    underlying=self.underlying,
                    exchange=self.underlying_exchange,
                    expiry_date=self.expiry,
                    strike_count=self.strike_count
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=8, require_oi=False, require_volume=False)
                if not valid:
                    self.logger.warning(f"Invalid chain: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])
                spot = safe_float(chain_resp.get("underlying_ltp"))

                # 1. EXIT MANAGEMENT FIRST
                if self.tracker.open_legs:
                    # Check Auto SL/TP/Time
                    exit_now, _, exit_reason = self.tracker.should_exit(chain)

                    # Check EOD
                    if not exit_now and self.check_eod_squareoff():
                        exit_now = True
                        exit_reason = "eod_squareoff"

                    if exit_now:
                        self._close_position(exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # Check EOD even if no tracked position (for safety)
                if self.check_eod_squareoff():
                     time.sleep(self.sleep_seconds)
                     continue

                # 2. CALCULATE INDICATORS
                straddle_premium = self.get_straddle_premium(chain)

                self.logger.info(format_kv(
                    spot=spot,
                    premium=straddle_premium,
                    can_trade=self.can_trade_now()
                ))

                # 3. ENTRY LOGIC
                signal_condition = (straddle_premium > self.min_straddle_prem) and self.can_trade_now()

                if not self.tracker.open_legs and self.debouncer.edge("entry_signal", signal_condition):
                    if self.limiter.allow():
                        self.logger.info(f"event=trade action=ENTRY signal_condition=True premium={straddle_premium}")

                        # Place Multi-Leg Order (BUY legs first for margin benefit)
                        legs_req = [
                            {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                        ]

                        order_resp = self.client.optionsmultiorder(
                            strategy=self.strategy_name,
                            underlying=self.underlying,
                            exchange=self.underlying_exchange,
                            expiry_date=self.expiry,
                            legs=legs_req
                        )

                        if order_resp.get("status") == "success":
                            # Process executed legs from response
                            executed_legs = order_resp.get("data", [])
                            self.all_open_legs = executed_legs

                            # Add ONLY SHORT legs to tracker to avoid false exits from protective buy legs
                            short_legs = []
                            short_entry_prices = []
                            for leg in executed_legs:
                                if leg.get("action", "").upper() == "SELL":
                                    short_legs.append(leg)
                                    short_entry_prices.append(leg.get("entry_price", 0.0))

                            if short_legs:
                                self.tracker.add_legs(short_legs, short_entry_prices, side="SELL")
                                self.limiter.record()
                                self.entered_today = True
                                self.logger.info(f"Position opened. Tracked {len(short_legs)} short legs.")
                            else:
                                self.logger.warning("Order succeeded but no SELL legs found to track.")
                        else:
                            self.logger.error(f"Order failed: {order_resp.get('message')}")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(self.sleep_seconds)


if __name__ == "__main__":
    try:
        strategy = NiftyIronCondorStrategy()
        strategy.run()
    except KeyboardInterrupt:
        print("Strategy stopped by user.", flush=True)
    except Exception as e:
        print(f"Fatal error: {e}", flush=True)
