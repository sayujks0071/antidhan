#!/usr/bin/env python3
"""
Best Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters an Iron Condor after 10 AM when straddle premium > 120, sells OTM2, buys OTM4.
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


class NiftyIronCondor:
    def __init__(self):
        self.logger = PrintLogger()

        # Configuration (from environment variables or sensible defaults)
        self.strategy_name = os.getenv("STRATEGY_NAME", "nifty_iron_condor")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = int(os.getenv("QUANTITY", "1"))
        self.strike_count = int(os.getenv("STRIKE_COUNT", "12"))

        # Strategy-specific logic variables
        self.sl_pct = float(os.getenv("SL_PCT", "40"))
        self.tp_pct = float(os.getenv("TP_PCT", "50"))
        self.max_hold_min = int(os.getenv("MAX_HOLD_MIN", "45"))
        self.min_straddle_premium = float(os.getenv("MIN_STRADDLE_PREMIUM", "120"))

        # Rate limits & Timing
        self.cooldown_seconds = int(os.getenv("COOLDOWN_SECONDS", "120"))
        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "30"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
        self.max_orders_per_day = int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
        self.max_orders_per_hour = int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

        # Utilities
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

        # State
        self.expiry = None
        self.last_expiry_refresh = 0
        self.entered_today = False
        self.last_trade_date = None

    def ensure_expiry(self):
        now = time.time()
        manual_override = os.getenv("EXPIRY_DATE")

        if manual_override:
            self.expiry = normalize_expiry(manual_override)
            return

        if self.expiry is None or (now - self.last_expiry_refresh) > self.expiry_refresh_sec:
            res = self.client.expiry(self.underlying, self.options_exchange, "options")
            if res.get("status") == "success" and res.get("data"):
                self.expiry = choose_nearest_expiry(res["data"])
                self.last_expiry_refresh = now
                self.logger.info(f"Resolved expiry: {self.expiry}")
            else:
                self.logger.warning("Failed to fetch expiry dates.")

    def _close_position(self, chain, exit_reason):
        """Close open multi-leg option position and reset tracker."""
        self.logger.info(f"event=trade action=CLOSE reason={exit_reason}")
        if not self.tracker.open_legs:
            return

        closing_legs = []
        # Sort to prioritize BUY to cover before SELL to close for margin efficiency
        sorted_legs = sorted(self.tracker.open_legs, key=lambda l: 0 if l["action"] == "SELL" else 1)

        for leg in sorted_legs:
            close_action = "BUY" if leg["action"] == "SELL" else "SELL"
            # We must use placesmartorder for individual leg closure,
            # but we need to know the specific option symbol to close.
            resp = self.client.placesmartorder(
                strategy=self.strategy_name,
                symbol=leg["symbol"],
                action=close_action,
                exchange=self.options_exchange,
                pricetype="MARKET",
                product=self.product,
                quantity=self.quantity,
                position_size=0  # target 0 to close
            )
            self.logger.info(format_kv(close_leg=leg["symbol"], action=close_action, resp=resp.get("status")))

        self.tracker.clear()

    def run(self):
        self.logger.info(f"Starting {self.strategy_name} strategy. Parameters: {self.quantity} qty.")
        while True:
            try:
                # 1. Market Hours Filter
                if not is_market_open():
                    self.logger.debug("Market is closed.")
                    time.sleep(self.sleep_seconds)
                    continue

                # 2. Expiry Management
                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(self.sleep_seconds)
                    continue

                # 3. Fetch Chain Data
                chain_resp = self.client.optionchain(
                    underlying=self.underlying,
                    exchange=self.underlying_exchange,
                    expiry_date=self.expiry,
                    strike_count=self.strike_count
                )
                valid, reason = is_chain_valid(chain_resp, min_strikes=8)
                if not valid:
                    self.logger.warning(f"Invalid chain: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])

                # 4. EXIT MANAGEMENT (Before Indicators)
                current_time = datetime.now()
                # Reset daily entry limit on new day
                if self.last_trade_date != current_time.date():
                    self.entered_today = False
                    self.last_trade_date = current_time.date()

                if self.tracker.open_legs:
                    # Time-based square-off
                    if current_time.hour == 15 and current_time.minute >= 15:
                        self._close_position(chain, "eod_squareoff")
                        time.sleep(self.sleep_seconds)
                        continue

                    exit_now, _, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # 5. CALCULATE INDICATORS
                atm_strike = chain_resp.get("atm_strike")
                spot_price = chain_resp.get("underlying_ltp")

                # Calculate Straddle Premium
                straddle_premium = 0.0
                for item in chain:
                    ce = item.get("ce", {})
                    pe = item.get("pe", {})
                    if ce.get("label") == "ATM":
                        straddle_premium += safe_float(ce.get("ltp"))
                        straddle_premium += safe_float(pe.get("ltp"))
                        break

                self.logger.debug(format_kv(spot=spot_price, atm=atm_strike, premium=straddle_premium))

                # 6. ENTRY LOGIC
                if not self.tracker.open_legs and not self.entered_today:
                    # Time filter: Enter after 10:00 AM, Before 2:30 PM
                    if current_time.hour < 10 or (current_time.hour == 14 and current_time.minute >= 30) or current_time.hour > 14:
                        time.sleep(self.sleep_seconds)
                        continue

                    # Strategy Filter: Straddle premium must be high enough
                    premium_ok = straddle_premium > self.min_straddle_premium

                    # Ensure rate limits
                    if self.debouncer.edge("ic_entry", premium_ok) and self.limiter.allow():
                        # Extract entry prices and symbols from chain
                        entry_prices = []
                        entry_symbols = []

                        otm2_ce = otm2_pe = otm4_ce = otm4_pe = None

                        for item in chain:
                            ce = item.get("ce", {})
                            pe = item.get("pe", {})
                            if ce.get("label") == "OTM2": otm2_ce = ce
                            if pe.get("label") == "OTM2": otm2_pe = pe
                            if ce.get("label") == "OTM4": otm4_ce = ce
                            if pe.get("label") == "OTM4": otm4_pe = pe

                        if not all([otm2_ce, otm2_pe, otm4_ce, otm4_pe]):
                            self.logger.warning("Could not find all required legs (OTM2/OTM4) in chain data.")
                            time.sleep(self.sleep_seconds)
                            continue

                        # BUY legs execute first, then SELL legs (for margin efficiency)
                        legs_def = [
                            {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                        ]

                        response = self.client.optionsmultiorder(
                            strategy=self.strategy_name,
                            underlying=self.underlying,
                            exchange=self.underlying_exchange,
                            expiry_date=self.expiry,
                            legs=legs_def
                        )

                        if response.get("status") == "success":
                            self.limiter.record()
                            self.entered_today = True

                            # Track positions
                            # Match the order of legs_def to store symbols & entry prices
                            entry_prices = [
                                safe_float(otm4_ce.get("ltp")),
                                safe_float(otm4_pe.get("ltp")),
                                safe_float(otm2_ce.get("ltp")),
                                safe_float(otm2_pe.get("ltp"))
                            ]

                            tracked_legs = [
                                {"symbol": otm4_ce.get("symbol"), "action": "BUY", "quantity": self.quantity},
                                {"symbol": otm4_pe.get("symbol"), "action": "BUY", "quantity": self.quantity},
                                {"symbol": otm2_ce.get("symbol"), "action": "SELL", "quantity": self.quantity},
                                {"symbol": otm2_pe.get("symbol"), "action": "SELL", "quantity": self.quantity},
                            ]

                            self.tracker.add_legs(tracked_legs, entry_prices, side="SELL")
                            self.logger.info(f"event=trade action=ENTRY status=success premium={straddle_premium}")
                        else:
                            self.logger.error(f"event=trade action=ENTRY status=failed reason={response.get('message')}")

            except Exception as e:
                self.logger.error(f"Error: {e}", exc_info=True)

            time.sleep(self.sleep_seconds)


if __name__ == "__main__":
    NiftyIronCondor().run()
