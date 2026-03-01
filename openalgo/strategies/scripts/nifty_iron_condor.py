#!/usr/bin/env python3
"""
[Nifty Iron Condor] - NIFTY Options (OpenAlgo Web UI Compatible)
Enters Iron Condor after 10 AM when ATM straddle > 120, using OTM2 short / OTM4 long wings.
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
    from trading_utils import is_market_open, calculate_straddle_premium
    from optionchain_utils import (
        OptionChainClient,
        OptionPositionTracker,
        choose_nearest_expiry,
        is_chain_valid,
        safe_float,
        safe_int,
    )
    from strategy_common import SignalDebouncer, TradeLimiter, format_kv
except ImportError as e:
    print(f"ERROR: Could not import strategy utilities: {e}", flush=True)
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


class NiftyIronCondorStrategy:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)

        # Configuration
        self.strategy_name = os.getenv("STRATEGY_NAME", "Nifty_Iron_Condor")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = safe_int(os.getenv("QUANTITY", "1"))
        self.strike_count = safe_int(os.getenv("STRIKE_COUNT", "10"))

        # Strategy specific params
        self.min_straddle_premium = safe_float(os.getenv("MIN_STRADDLE", "120"))
        self.sl_pct = safe_float(os.getenv("SL_PCT", "40"))
        self.tp_pct = safe_float(os.getenv("TP_PCT", "50"))
        self.max_hold_min = safe_int(os.getenv("MAX_HOLD_MIN", "45"))

        # Timing configurations
        self.cooldown_seconds = safe_int(os.getenv("COOLDOWN_SECONDS", "300"))
        self.sleep_seconds = safe_int(os.getenv("SLEEP_SECONDS", "30"))
        self.expiry_refresh_sec = safe_int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))

        # State
        self.expiry_date = os.getenv("EXPIRY_DATE")
        self.last_expiry_fetch = 0
        self.entered_today = False
        self.last_trade_date = None

        # Components
        self.tracker = OptionPositionTracker(
            sl_pct=self.sl_pct,
            tp_pct=self.tp_pct,
            max_hold_min=self.max_hold_min
        )
        self.limiter = TradeLimiter(
            max_per_day=1,
            max_per_hour=1,
            cooldown_seconds=self.cooldown_seconds
        )
        self.debouncer = SignalDebouncer()

        self.logger.info(f"Initialized {self.strategy_name}")
        self.logger.info(f"Config: SL={self.sl_pct}%, TP={self.tp_pct}%, MaxHold={self.max_hold_min}m")

    def ensure_expiry(self):
        """Fetch/refresh nearest expiry date periodically."""
        now = time.time()
        if self.expiry_date and (now - self.last_expiry_fetch < self.expiry_refresh_sec):
            return

        try:
            res = self.client.expiry(self.underlying, self.options_exchange, "options")
            if res and res.get("status") == "success":
                dates = res.get("data", [])
                if dates:
                    nearest = choose_nearest_expiry(dates)
                    if nearest and nearest != self.expiry_date:
                        self.expiry_date = nearest
                        self.last_expiry_fetch = now
                        self.logger.info(f"Selected nearest expiry: {self.expiry_date}")
        except Exception as e:
            self.logger.error(f"Failed to fetch expiry: {e}")

    def can_trade(self):
        """Check entry conditions based on time and limits."""
        now = datetime.now()

        # Reset daily tracking
        if self.last_trade_date != now.date():
            self.entered_today = False
            self.last_trade_date = now.date()

        if self.entered_today:
            return False

        current_time = now.time()
        # Enter after 10:00 AM, up to 2:30 PM
        if current_time < datetime.strptime("10:00", "%H:%M").time():
            return False

        if current_time > datetime.strptime("14:30", "%H:%M").time():
            return False

        return self.limiter.allow()

    def check_eod_exit(self):
        """Square-off before 3:15 PM."""
        now = datetime.now().time()
        eod_time = datetime.strptime("15:15", "%H:%M").time()
        return now >= eod_time

    def _close_position(self, chain, reason):
        """Closes all legs of the Iron Condor."""
        if not self.tracker.open_legs:
            return

        self.logger.info(f"Closing position. Reason: {reason}")

        close_legs = []
        for leg in self.tracker.open_legs:
            close_legs.append({
                "offset": leg["offset"],
                "option_type": leg["option_type"],
                "action": "BUY" if leg["action"] == "SELL" else "SELL",
                "quantity": leg["quantity"],
                "product": leg["product"]
            })

        # Order of execution for closing: SELL long legs first, then BUY short legs
        sell_legs = [l for l in close_legs if l["action"] == "SELL"]
        buy_legs = [l for l in close_legs if l["action"] == "BUY"]
        ordered_close_legs = sell_legs + buy_legs

        try:
            resp = self.client.optionsmultiorder(
                strategy=self.strategy_name,
                underlying=self.underlying,
                exchange=self.options_exchange,
                expiry_date=self.expiry_date,
                legs=ordered_close_legs
            )
            self.logger.info(f"event=trade action=CLOSE reason={reason} response={resp}")
        except Exception as e:
            self.logger.error(f"Failed to close position: {e}")

        self.tracker.clear()

    def run(self):
        self.logger.info(f"Starting {self.strategy_name} main loop...")

        while True:
            try:
                if not is_market_open():
                    self.logger.debug("Market is closed. Sleeping.")
                    time.sleep(self.sleep_seconds)
                    continue

                self.ensure_expiry()
                if not self.expiry_date:
                    time.sleep(self.sleep_seconds)
                    continue

                # Fetch Option Chain
                chain_resp = self.client.optionchain(
                    underlying=self.underlying,
                    exchange=self.underlying_exchange,
                    expiry_date=self.expiry_date,
                    strike_count=self.strike_count
                )

                valid, reason = is_chain_valid(chain_resp, min_strikes=6, require_ltp=True)
                if not valid:
                    self.logger.debug(f"Invalid chain: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])
                spot = chain_resp.get("underlying_ltp", 0.0)

                # =======================================================
                # 1. EXIT MANAGEMENT
                # =======================================================
                if self.tracker.open_legs:
                    # Check EOD first
                    if self.check_eod_exit():
                        self._close_position(chain, "EOD_SQUAREOFF")
                        time.sleep(self.sleep_seconds)
                        continue

                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # =======================================================
                # 2. ENTRY LOGIC
                # =======================================================
                if not self.tracker.open_legs and self.can_trade():
                    straddle_prem = calculate_straddle_premium(chain)

                    self.logger.debug(format_kv(
                        spot=spot,
                        straddle=straddle_prem,
                        min_req=self.min_straddle_premium
                    ))

                    signal = straddle_prem > self.min_straddle_premium
                    trigger = self.debouncer.edge("enter_ic", signal)

                    if trigger:
                        self.logger.info(f"Signal triggered: straddle={straddle_prem} > {self.min_straddle_premium}")

                        # Define Iron Condor Legs
                        # Buy OTM4, Sell OTM2
                        legs = [
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
                                expiry_date=self.expiry_date,
                                legs=legs
                            )
                            self.logger.info(f"event=trade action=OPEN_IC response={resp}")

                            # Assuming execution was successful and getting entry prices from chain
                            entry_prices = {}
                            for leg in legs:
                                for strike_item in chain:
                                    opt_data = strike_item.get(leg["option_type"].lower(), {})
                                    if opt_data.get("label") == leg["offset"]:
                                        entry_prices[leg["offset"] + leg["option_type"]] = opt_data.get("ltp", 0.0)
                                        break

                            self.tracker.add_legs(legs, entry_prices, side="SELL") # We are net selling
                            self.entered_today = True
                            self.limiter.record()

                        except Exception as e:
                            self.logger.error(f"Failed to place Iron Condor order: {e}")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}", exc_info=True)

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    NiftyIronCondorStrategy().run()
