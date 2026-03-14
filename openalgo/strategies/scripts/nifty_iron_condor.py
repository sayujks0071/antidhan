#!/usr/bin/env python3
"""
Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters Iron Condor after 10 AM if premium > 120, 40% SL, 50% TP, max hold 45 mins.
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


class NiftyIronCondor:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)

        # Configs
        self.strategy_name = os.getenv("STRATEGY_NAME", "Nifty_Iron_Condor")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = int(os.getenv("QUANTITY", "1"))
        self.strike_count = int(os.getenv("STRIKE_COUNT", "12"))

        # Risk Management Configs
        self.sl_pct = float(os.getenv("SL_PCT", "40"))
        self.tp_pct = float(os.getenv("TP_PCT", "50"))
        self.max_hold_min = int(os.getenv("MAX_HOLD_MIN", "45"))

        # Timeframes & Intervals
        self.cooldown_seconds = int(os.getenv("COOLDOWN_SECONDS", "120"))
        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "30"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
        self.max_orders_per_day = int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
        self.max_orders_per_hour = int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

        # Strategy specific params
        self.min_straddle_premium = float(os.getenv("MIN_STRADDLE_PREMIUM", "120.0"))
        self.sell_offset = os.getenv("SELL_OFFSET", "OTM2")
        self.buy_offset = os.getenv("BUY_OFFSET", "OTM4")

        # Expiry management
        self.expiry_date = os.getenv("EXPIRY_DATE", None)
        self.last_expiry_refresh = 0

        # State
        self.entered_today = False
        self.reset_date = datetime.now().date()
        self.all_open_legs = []

        # Utils
        self.tracker = OptionPositionTracker(sl_pct=self.sl_pct, tp_pct=self.tp_pct, max_hold_min=self.max_hold_min)
        self.limiter = TradeLimiter(
            max_per_day=self.max_orders_per_day,
            max_per_hour=self.max_orders_per_hour,
            cooldown_seconds=self.cooldown_seconds
        )
        self.debouncer = SignalDebouncer()

        self.logger.info(f"Initialized {self.strategy_name} for {self.underlying}")

    def ensure_expiry(self):
        """Auto-resolves nearest expiry periodically if not explicitly set."""
        now = time.time()
        if self.expiry_date and (now - self.last_expiry_refresh < self.expiry_refresh_sec):
            return

        res = self.client.expiry(self.underlying, self.options_exchange, "options")
        if res and res.get("status") == "success" and res.get("data"):
            nearest = choose_nearest_expiry(res["data"])
            if nearest:
                if self.expiry_date != nearest:
                    self.logger.info(f"Setting target expiry to {nearest}")
                self.expiry_date = nearest
                self.last_expiry_refresh = now
            else:
                self.logger.warning("Could not determine nearest expiry from API.")
        else:
            self.logger.warning("Failed to fetch expiries from API.")

    def _check_reset(self):
        now = datetime.now().date()
        if now != self.reset_date:
            self.entered_today = False
            self.reset_date = now

    def can_trade(self):
        self._check_reset()
        if self.entered_today:
            return False

        # Entry time window: 10:00 AM - 2:30 PM IST
        now = datetime.now()
        current_time = now.time()

        start_time = dt_time(10, 0)
        end_time = dt_time(14, 30)

        if not (start_time <= current_time <= end_time):
            return False

        return self.limiter.allow()

    def _close_position(self, chain, reason):
        """Closes all open legs."""
        if not self.all_open_legs:
            return

        self.logger.info(f"Closing position. Reason: {reason}")

        # Close each leg explicitly since the optionsmultiorder offset approach uses relative offsets
        for leg in self.all_open_legs:
            # Reverse the action to close
            close_action = "BUY" if leg["action"] == "SELL" else "SELL"

            # Use placesmartorder to close position by specifying position_size=0
            try:
                # Need to use placesmartorder API since it's a standalone script
                from trading_utils import APIClient
                api_client = APIClient(api_key=API_KEY, host=HOST)

                resp = api_client.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=leg["symbol"],
                    action=close_action,
                    exchange=self.options_exchange,
                    pricetype="MARKET",
                    product=leg["product"],
                    quantity=leg["quantity"],
                    position_size=0
                )
                self.logger.info(f"Trade response for closing leg {leg['symbol']}: {resp}")
            except Exception as e:
                self.logger.error(f"Error closing leg {leg['symbol']}: {e}")

        self.tracker.clear()
        self.all_open_legs = []

    def run(self):
        self.logger.info("Starting Strategy Loop...")
        while True:
            try:
                self._check_reset()

                if not is_market_open():
                    time.sleep(self.sleep_seconds)
                    continue

                self.ensure_expiry()
                if not self.expiry_date:
                    time.sleep(self.sleep_seconds)
                    continue

                chain_resp = self.client.optionchain(
                    underlying=self.underlying,
                    exchange=self.underlying_exchange,
                    expiry_date=self.expiry_date,
                    strike_count=self.strike_count
                )

                valid, valid_reason = is_chain_valid(chain_resp, min_strikes=10, require_oi=True)
                if not valid:
                    self.logger.warning(f"Chain invalid: {valid_reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])
                atm_strike = chain_resp.get("atm_strike")

                # Time Check for EOD Exit (before 3:15 PM)
                current_time = datetime.now().time()
                eod_time = dt_time(15, 15)
                is_eod = current_time >= eod_time

                # 1. EXIT MANAGEMENT
                if self.all_open_legs:
                    if is_eod:
                        self._close_position(chain, "EOD Exit")
                        time.sleep(self.sleep_seconds)
                        continue

                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # 2. CALCULATE INDICATORS
                straddle_premium = 0
                if atm_strike:
                    for item in chain:
                        if item.get("strike") == atm_strike:
                            ce_ltp = safe_float(item.get("ce", {}).get("ltp", 0))
                            pe_ltp = safe_float(item.get("pe", {}).get("ltp", 0))
                            straddle_premium = ce_ltp + pe_ltp
                            break
                    self.logger.debug(format_kv(spot=atm_strike, premium=straddle_premium))
                else:
                    self.logger.debug("Could not determine ATM strike")

                # 3. ENTRY LOGIC
                if not self.all_open_legs and not is_eod and self.can_trade():
                    signal = self.debouncer.edge("entry_signal", straddle_premium > self.min_straddle_premium)

                    if signal:
                        self.logger.info(f"Entry Signal: Premium {straddle_premium:.2f} > {self.min_straddle_premium}")

                        # Define the legs for Iron Condor
                        # BUY OTM4 CE/PE, SELL OTM2 CE/PE
                        legs_req = [
                            {"offset": self.buy_offset, "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": self.buy_offset, "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": self.sell_offset, "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                            {"offset": self.sell_offset, "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                        ]

                        self.logger.info("Placing Multi-leg order for Iron Condor...")
                        resp = self.client.optionsmultiorder(
                            strategy=self.strategy_name,
                            underlying=self.underlying,
                            exchange=self.options_exchange,
                            expiry_date=self.expiry_date,
                            legs=legs_req
                        )

                        self.logger.info(f"event=trade response={resp}")

                        if resp.get("status") == "success" and resp.get("data"):
                            executed_legs = resp.get("data", {}).get("legs", [])
                            # Extract executed legs and their execution prices
                            if executed_legs:
                                self.all_open_legs = executed_legs
                                # Track the SELL legs for SL/TP based on memory:
                                # "ensure you filter the execution legs to only include short ('SELL') legs before calling tracker.add_legs()"
                                short_legs = [l for l in executed_legs if l.get("action") == "SELL"]
                                entry_prices = [l.get("average_price", l.get("price", 0)) for l in short_legs]

                                self.tracker.add_legs(short_legs, entry_prices, side="SELL")
                                self.entered_today = True
                                self.limiter.record()
                                self.logger.info("Position Tracked Successfully.")
                            else:
                                self.logger.warning("Order successful but no executed legs returned.")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}", exc_info=True)

            time.sleep(self.sleep_seconds)


if __name__ == "__main__":
    NiftyIronCondor().run()
