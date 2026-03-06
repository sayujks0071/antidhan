#!/usr/bin/env python3
"""
Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters after 10 AM (premium > 120), selling OTM2/buying OTM4, with 40% SL, 50% TP, and a 45-minute maximum hold.
CHANGELOG:
- 2026-02-23: Initial implementation based on Web UI boilerplate.
"""
import os
import sys
import time
from datetime import datetime, time as dt_time

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
sys.path.insert(0, utils_dir)
sys.path.insert(0, root_dir)

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
    from strategy_common import SignalDebouncer, TradeLedger, TradeLimiter, format_kv
except ImportError:
    print("ERROR: Could not import strategy utilities.", flush=True)
    sys.exit(1)


class PrintLogger:
    def info(self, msg): print(msg, flush=True)
    def warning(self, msg): print(msg, flush=True)
    def error(self, msg, exc_info=False): print(msg, flush=True)
    def debug(self, msg): print(msg, flush=True)


# API Key retrieval (MANDATORY)
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

        # Configuration Section
        self.strategy_name = os.getenv("STRATEGY_NAME", "Nifty_Iron_Condor")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = int(os.getenv("QUANTITY", "1"))
        self.strike_count = int(os.getenv("STRIKE_COUNT", "12"))

        # Risk Management Parameters
        self.sl_pct = float(os.getenv("SL_PCT", "40"))
        self.tp_pct = float(os.getenv("TP_PCT", "50"))
        self.max_hold_min = int(os.getenv("MAX_HOLD_MIN", "45"))
        self.cooldown_seconds = int(os.getenv("COOLDOWN_SECONDS", "300"))
        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "30"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
        self.max_orders_per_day = int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
        self.max_orders_per_hour = int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

        # Strategy specific params
        self.min_straddle_premium = float(os.getenv("MIN_STRADDLE_PREMIUM", "120"))

        # Clients and Utils
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

        # State
        self.expiry = None
        self.last_expiry_refresh = 0
        self.full_position_legs = []  # Keep track of all 4 legs (tracker only gets SELL legs for correct PNL)

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_refresh) > self.expiry_refresh_sec:
            override = os.getenv("EXPIRY_DATE")
            if override:
                self.expiry = normalize_expiry(override)
                self.last_expiry_refresh = now
                self.logger.info(f"Using overridden expiry: {self.expiry}")
                return

            try:
                res = self.client.expiry(self.underlying, self.options_exchange, "options")
                if res and res.get("status") == "success":
                    dates = res.get("data", [])
                    self.expiry = choose_nearest_expiry(dates)
                    self.last_expiry_refresh = now
                    self.logger.info(f"Resolved nearest expiry: {self.expiry}")
            except Exception as e:
                self.logger.error(f"Failed to fetch expiry: {e}")

    def _close_position(self, chain, reason):
        if not self.full_position_legs:
            return

        self.logger.info(f"event=trade action=CLOSE reason={reason}")

        close_legs = []
        for leg in self.full_position_legs:
            # Reverse action for closing
            close_action = "SELL" if leg["action"] == "BUY" else "BUY"
            close_legs.append({
                "offset": leg["offset"],
                "option_type": leg["option_type"],
                "action": close_action,
                "quantity": leg["quantity"],
                "product": leg["product"]
            })

        try:
            resp = self.client.optionsmultiorder(
                strategy=self.strategy_name,
                underlying=self.underlying,
                exchange=self.options_exchange,
                expiry_date=self.expiry,
                legs=close_legs
            )
            self.logger.info(f"Close response: {resp}")
        except Exception as e:
            self.logger.error(f"Error placing close order: {e}")

        self.tracker.clear()
        self.full_position_legs = []

    def run(self):
        self.logger.info(f"Starting {self.strategy_name}...")
        self.logger.info(format_kv(
            underlying=self.underlying,
            sl_pct=self.sl_pct,
            tp_pct=self.tp_pct,
            max_hold=self.max_hold_min,
            min_premium=self.min_straddle_premium
        ))

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

                valid, reason = is_chain_valid(chain_resp, min_strikes=10, require_oi=False, require_volume=False)
                if not valid:
                    self.logger.debug(f"Invalid chain: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])
                spot = chain_resp.get("underlying_ltp", 0.0)

                # Check EOD Exit (before 3:15 PM)
                now_time = datetime.now().time()
                eod_time = dt_time(15, 15)

                # EXIT MANAGEMENT FIRST
                if self.tracker.open_legs:
                    if now_time >= eod_time:
                        self._close_position(chain, "eod_square_off")
                        time.sleep(self.sleep_seconds)
                        continue

                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # ENTRY LOGIC
                # Only enter after 10 AM and before 3 PM
                entry_start = dt_time(10, 0)
                entry_end = dt_time(15, 0)

                if not self.tracker.open_legs and self.limiter.allow() and entry_start <= now_time <= entry_end:

                    # Calculate ATM Straddle Premium
                    atm_ce_ltp = 0
                    atm_pe_ltp = 0

                    for item in chain:
                        ce = item.get("ce", {})
                        pe = item.get("pe", {})
                        if ce.get("label") == "ATM":
                            atm_ce_ltp = safe_float(ce.get("ltp"))
                        if pe.get("label") == "ATM":
                            atm_pe_ltp = safe_float(pe.get("ltp"))

                    straddle_premium = atm_ce_ltp + atm_pe_ltp

                    self.logger.debug(format_kv(spot=spot, straddle=straddle_premium))

                    if straddle_premium > self.min_straddle_premium:
                        # Extract symbols and prices for tracker
                        sell_legs_tracker = []
                        entry_prices_tracker = []

                        full_legs = []

                        # Find required offsets to get symbols and LTPs
                        for item in chain:
                            ce = item.get("ce", {})
                            pe = item.get("pe", {})

                            ce_label = ce.get("label", "")
                            pe_label = pe.get("label", "")

                            if ce_label == "OTM2":
                                sell_legs_tracker.append({
                                    "symbol": ce.get("symbol"),
                                    "action": "SELL",
                                    "quantity": self.quantity
                                })
                                entry_prices_tracker.append(safe_float(ce.get("ltp")))

                            if pe_label == "OTM2":
                                sell_legs_tracker.append({
                                    "symbol": pe.get("symbol"),
                                    "action": "SELL",
                                    "quantity": self.quantity
                                })
                                entry_prices_tracker.append(safe_float(pe.get("ltp")))

                        # Verify we found the required legs
                        if len(sell_legs_tracker) == 2:
                            self.logger.info(f"event=trade action=ENTRY strategy={self.strategy_name} straddle={straddle_premium}")

                            # Define API legs (BUY first for margin benefit)
                            api_legs = [
                                {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                                {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                                {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                                {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                            ]

                            try:
                                resp = self.client.optionsmultiorder(
                                    strategy=self.strategy_name,
                                    underlying=self.underlying,
                                    exchange=self.options_exchange,
                                    expiry_date=self.expiry,
                                    legs=api_legs
                                )
                                self.logger.info(f"Entry response: {resp}")

                                # Setup tracking
                                self.limiter.record()
                                self.full_position_legs = api_legs

                                # Add only SELL legs to tracker to avoid false premature exits on protective buy wings
                                self.tracker.add_legs(sell_legs_tracker, entry_prices_tracker, side="SELL")

                                self.logger.info(format_kv(
                                    msg="Position opened",
                                    premium=straddle_premium,
                                    tracker_legs=len(sell_legs_tracker)
                                ))

                            except Exception as e:
                                self.logger.error(f"Error placing entry order: {e}")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(self.sleep_seconds)


if __name__ == "__main__":
    NiftyIronCondorStrategy().run()
