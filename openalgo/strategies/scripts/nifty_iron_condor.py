#!/usr/bin/env python3
"""
NIFTY Iron Condor Strategy - NIFTY Options (OpenAlgo Web UI Compatible)
Enters an Iron Condor after 10 AM if straddle premium > 120, sells OTM2 / buys OTM4, 40% SL, 50% TP.
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
sys.path.insert(0, root_dir)
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
        self.strategy_name = os.getenv("STRATEGY_NAME", "NIFTY_IRON_CONDOR")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = int(os.getenv("QUANTITY", "1"))
        self.strike_count = int(os.getenv("STRIKE_COUNT", "12"))

        # Risk Management
        self.sl_pct = float(os.getenv("SL_PCT", "40"))
        self.tp_pct = float(os.getenv("TP_PCT", "50"))
        self.max_hold_min = int(os.getenv("MAX_HOLD_MIN", "45"))

        # Strategy Parameters
        self.min_straddle_premium = float(os.getenv("MIN_STRADDLE_PREMIUM", "120"))

        # Time Management
        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "30"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))

        # Limits
        max_orders_per_day = int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
        max_orders_per_hour = int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))
        cooldown_seconds = int(os.getenv("COOLDOWN_SECONDS", "120"))

        self.tracker = OptionPositionTracker(
            sl_pct=self.sl_pct,
            tp_pct=self.tp_pct,
            max_hold_min=self.max_hold_min
        )
        self.limiter = TradeLimiter(
            max_per_day=max_orders_per_day,
            max_per_hour=max_orders_per_hour,
            cooldown_seconds=cooldown_seconds
        )
        self.debouncer = SignalDebouncer()

        # State
        self.expiry = None
        self.last_expiry_refresh = 0
        self.entered_today = False
        self.last_date = None

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_refresh) > self.expiry_refresh_sec:
            try:
                res = self.client.expiry(self.underlying, self.options_exchange, "options")
                if res and res.get("status") == "success" and res.get("data"):
                    nearest = choose_nearest_expiry(res["data"])
                    if nearest:
                        self.expiry = normalize_expiry(nearest)
                        self.last_expiry_refresh = now
                        self.logger.info(f"Resolved Expiry: {self.expiry}")
            except Exception as e:
                self.logger.error(f"Error fetching expiry: {e}")

    def can_trade(self):
        # Only check entry time and limits
        now = datetime.now()
        current_time = now.time()

        # Reset daily entry limit if it's a new day
        if self.last_date != now.date():
            self.entered_today = False
            self.last_date = now.date()

        if self.entered_today:
            return False

        if current_time < dt_time(10, 0):
            return False

        if current_time >= dt_time(15, 15):
            return False

        if not self.limiter.allow():
            return False

        return True

    def calculate_straddle_premium(self, chain, atm_strike):
        for item in chain:
            if item.get("strike") == atm_strike:
                ce_ltp = safe_float(item.get("ce", {}).get("ltp"))
                pe_ltp = safe_float(item.get("pe", {}).get("ltp"))
                return ce_ltp + pe_ltp
        return 0.0

    def get_ltp_by_offset(self, chain, option_type, offset):
        for item in chain:
            opt = item.get(option_type.lower(), {})
            if opt.get("label") == offset:
                return safe_float(opt.get("ltp"))
        return 0.0

    def run(self):
        self.logger.info(f"Starting {self.strategy_name} Strategy Loop")

        while True:
            try:
                if not is_market_open(self.underlying_exchange):
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
                    self.logger.warning(f"Invalid chain: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])
                atm_strike = safe_float(chain_resp.get("atm_strike"))
                spot_price = safe_float(chain_resp.get("underlying_ltp"))

                # EOD Square-off
                current_time = datetime.now().time()
                if current_time >= dt_time(15, 15) and self.tracker.open_legs:
                    self._close_position(chain, "EOD_Square_off")
                    time.sleep(self.sleep_seconds)
                    continue

                # EXIT MANAGEMENT
                if self.tracker.open_legs:
                    exit_now, legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                    # Continue monitoring without entering new positions
                    time.sleep(self.sleep_seconds)
                    continue

                # ENTRY LOGIC
                if not self.tracker.open_legs and self.can_trade():
                    straddle_premium = self.calculate_straddle_premium(chain, atm_strike)

                    self.logger.info(format_kv(
                        spot=spot_price,
                        atm=atm_strike,
                        straddle=straddle_premium,
                        req_straddle=self.min_straddle_premium
                    ))

                    signal = straddle_premium > self.min_straddle_premium

                    if self.debouncer.edge("enter_ic", signal):
                        self.logger.info("Signal generated: Entering Iron Condor")

                        # Define legs: Sell OTM2, Buy OTM4
                        legs_config = [
                            # BUY legs first for margin benefit
                            {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            # SELL legs
                            {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                        ]

                        resp = self.client.optionsmultiorder(
                            strategy=self.strategy_name,
                            underlying=self.underlying,
                            exchange=self.underlying_exchange,
                            expiry_date=self.expiry,
                            legs=legs_config
                        )

                        self.logger.info(f"Trade response: {resp}")

                        if resp and resp.get("status") == "success":
                            self.limiter.record()
                            self.entered_today = True

                            # Track position
                            # Extract exact symbols from chain to track
                            tracked_legs = []
                            entry_prices = []

                            for leg_conf in legs_config:
                                offset = leg_conf["offset"]
                                opt_type = leg_conf["option_type"]

                                # Find symbol in chain
                                symbol = None
                                ltp = 0.0
                                for item in chain:
                                    opt = item.get(opt_type.lower(), {})
                                    if opt.get("label") == offset:
                                        symbol = opt.get("symbol")
                                        ltp = safe_float(opt.get("ltp"))
                                        break

                                if symbol:
                                    tracked_legs.append({
                                        "symbol": symbol,
                                        "action": leg_conf["action"],
                                        "quantity": leg_conf["quantity"],
                                        "product": leg_conf["product"],
                                        "offset": offset,
                                        "option_type": opt_type
                                    })
                                    entry_prices.append(ltp)
                                else:
                                    self.logger.error(f"Could not find symbol for {offset} {opt_type}")

                            if len(tracked_legs) == 4:
                                # Track short legs for SL/TP as per premium selling logic
                                short_legs = []
                                short_prices = []
                                for i, leg in enumerate(tracked_legs):
                                    if leg["action"] == "SELL":
                                        short_legs.append(leg)
                                        short_prices.append(entry_prices[i])

                                self.tracker.add_legs(short_legs, short_prices, side="SELL")
                                # Note: the actual open_legs in tracker is used for closing in _close_position
                                # But we want to close ALL legs.
                                # Let's add all legs to tracker but only calculate PnL on SELL legs?
                                # Actually, memory states: "filter the execution legs to only include short ('SELL') legs before calling `tracker.add_legs()`".
                                # And when closing, we need to close all. If tracker only has short legs, we can't close buy legs easily.
                                # Let's add all legs, but memory says "filter the execution legs to only include short ('SELL') legs before calling `tracker.add_legs()`. Failure to do so may cause false premature exits triggered by protective buy legs."
                                # Ok, if tracker only tracks SELL legs, then _close_position must close ALL 4 legs!
                                # Let's store all 4 legs in strategy and close them all.
                                self.all_position_legs = tracked_legs
                            else:
                                self.logger.error("Failed to track all 4 legs.")

            except Exception as e:
                self.logger.error(f"Error: {e}")

            time.sleep(self.sleep_seconds)

    # Override _close_position to close ALL legs we opened, even if tracker only knows about SHORT legs
    def _close_position(self, chain, reason):
        self.logger.info(f"Closing position. Reason: {reason}")

        # Close all legs
        for leg in getattr(self, "all_position_legs", self.tracker.open_legs):
            close_action = "BUY" if leg["action"] == "SELL" else "SELL"
            try:
                resp = self.client.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=leg["symbol"],
                    action=close_action,
                    exchange=self.options_exchange,
                    pricetype="MARKET",
                    product=leg["product"],
                    quantity=leg["quantity"],
                    position_size=0
                )
                self.logger.info(f"Closed leg {leg['symbol']} with action {close_action}. Response: {resp}")
            except Exception as e:
                self.logger.error(f"Error closing leg {leg['symbol']}: {e}")

        self.tracker.clear()
        self.all_position_legs = []

if __name__ == "__main__":
    NiftyIronCondorStrategy().run()
