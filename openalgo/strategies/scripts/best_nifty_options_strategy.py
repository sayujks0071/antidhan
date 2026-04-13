#!/usr/bin/env python3
"""
Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters after 10 AM when straddle premium > 120, sells OTM2, buys OTM4.
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
sys.path.insert(0, utils_dir)
sys.path.insert(0, strategies_dir)
sys.path.insert(0, root_dir)

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
        self.strategy_name = os.getenv("STRATEGY_NAME", "NiftyIronCondor")
        self.underlying = os.getenv("UNDERLYING", "NIFTY")
        self.underlying_exchange = os.getenv("UNDERLYING_EXCHANGE", "NSE_INDEX")
        self.options_exchange = os.getenv("OPTIONS_EXCHANGE", "NFO")
        self.product = os.getenv("PRODUCT", "MIS")
        self.quantity = int(os.getenv("QUANTITY", "1"))
        self.strike_count = int(os.getenv("STRIKE_COUNT", "12"))

        self.sl_pct = float(os.getenv("SL_PCT", "40.0"))
        self.tp_pct = float(os.getenv("TP_PCT", "50.0"))
        self.max_hold_min = int(os.getenv("MAX_HOLD_MIN", "45"))

        self.cooldown_seconds = int(os.getenv("COOLDOWN_SECONDS", "120"))
        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "30"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))

        self.max_orders_per_day = int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
        self.max_orders_per_hour = int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

        self.manual_expiry = os.getenv("EXPIRY_DATE", "")

        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)
        self.tracker = OptionPositionTracker(sl_pct=self.sl_pct, tp_pct=self.tp_pct, max_hold_min=self.max_hold_min)
        self.limiter = TradeLimiter(
            max_per_day=self.max_orders_per_day,
            max_per_hour=self.max_orders_per_hour,
            cooldown_seconds=self.cooldown_seconds
        )
        self.debouncer = SignalDebouncer()

        self.expiry = None
        self.last_expiry_refresh = 0

        self.logger.info(f"Initialized {self.strategy_name} for {self.underlying}")

    def ensure_expiry(self):
        now = time.time()
        if self.manual_expiry:
            self.expiry = self.manual_expiry
            return

        if not self.expiry or (now - self.last_expiry_refresh > self.expiry_refresh_sec):
            try:
                res = self.client.expiry(self.underlying, self.options_exchange, "options")
                if res and res.get("status") == "success" and res.get("data"):
                    dates = res.get("data")
                    self.expiry = choose_nearest_expiry(dates)
                    self.last_expiry_refresh = now
                    self.logger.info(f"Resolved nearest expiry: {self.expiry}")
                else:
                    self.logger.warning("Failed to fetch expiry dates")
            except Exception as e:
                self.logger.error(f"Error fetching expiry: {e}")

    def can_trade_time(self):
        now = datetime.now()
        # Enters after 10 AM, and not after 3:00 PM
        if now.hour < 10:
            return False
        if now.hour >= 15:
            return False
        return True

    def should_eod_square_off(self):
        now = datetime.now()
        # Exits all positions by 3:15 PM (15:15)
        if now.hour > 15 or (now.hour == 15 and now.minute >= 15):
            return True
        return False

    def get_straddle_premium(self, chain):
        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})
            if ce.get("label") == "ATM" or pe.get("label") == "ATM":
                ce_ltp = safe_float(ce.get("ltp"))
                pe_ltp = safe_float(pe.get("ltp"))
                return ce_ltp + pe_ltp
        return 0.0

    def get_leg_price(self, chain, option_type, offset):
        for item in chain:
            opt = item.get(option_type.lower(), {})
            if opt.get("label") == offset:
                return safe_float(opt.get("ltp"))
        return 0.0

    def get_leg_symbol(self, chain, option_type, offset):
        for item in chain:
            opt = item.get(option_type.lower(), {})
            if opt.get("label") == offset:
                return opt.get("symbol")
        return None

    def _close_position(self, chain, reason):
        self.logger.info(format_kv(event="trade", action="close_position", reason=reason))
        if not self.tracker.open_legs:
            return

        # Sort legs: BUY to cover (closing SELL legs) first!
        legs_to_close = []
        for leg in self.tracker.open_legs:
            close_act = "BUY" if leg.get("action") == "SELL" else "SELL"
            legs_to_close.append({
                "symbol": leg.get("symbol"),
                "action": close_act,
                "quantity": leg.get("quantity", self.quantity),
                "product": leg.get("product", self.product),
            })

        legs_to_close.sort(key=lambda x: 0 if x["action"] == "BUY" else 1)

        for cl in legs_to_close:
            try:
                if cl["symbol"]:
                    resp = self.api_client.placesmartorder(
                        strategy=self.strategy_name,
                        symbol=cl["symbol"],
                        action=cl["action"],
                        exchange=self.options_exchange,
                        pricetype="MARKET",
                        product=cl["product"],
                        quantity=cl["quantity"],
                        position_size=0
                    )
                    self.logger.info(f"Closed leg {cl['symbol']} {cl['action']}: {resp}")
                else:
                    self.logger.warning(f"Could not close leg, symbol missing: {cl}")
            except Exception as e:
                self.logger.error(f"Error closing leg {cl['symbol']}: {e}")

        self.tracker.clear()

    def run(self):
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
                    self.logger.debug(f"Chain invalid: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])

                # EXIT MANAGEMENT
                if self.tracker.open_legs:
                    # EOD Exit
                    if self.should_eod_square_off():
                        self._close_position(chain, "eod_square_off")
                        time.sleep(self.sleep_seconds)
                        continue

                    exit_now, _legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # ENTRY LOGIC
                if not self.tracker.open_legs and self.limiter.allow() and self.can_trade_time() and not self.should_eod_square_off():
                    premium = self.get_straddle_premium(chain)
                    self.logger.debug(format_kv(spot=chain_resp.get("underlying_ltp"), premium=premium))

                    signal_condition = premium > 120
                    signal = self.debouncer.edge("straddle_premium", signal_condition)

                    if signal:
                        # Construct legs: Buy OTM4 first, Sell OTM2 second
                        entry_legs = [
                            {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                            {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                        ]

                        self.logger.info(format_kv(event="trade", action="entry_signal", premium=premium))

                        resp = self.client.optionsmultiorder(
                            strategy=self.strategy_name,
                            underlying=self.underlying,
                            exchange=self.underlying_exchange,
                            expiry_date=self.expiry,
                            legs=entry_legs
                        )

                        self.logger.info(f"Trade response: {resp}")

                        # Add legs to tracker even if response checking is loose, but let's assume success if resp isn't error
                        if resp and resp.get("status") == "success":
                            self.limiter.record()

                            tracker_legs = []
                            entry_prices = []
                            for l in entry_legs:
                                sym = self.get_leg_symbol(chain, l["option_type"], l["offset"])
                                pr = self.get_leg_price(chain, l["option_type"], l["offset"])
                                l_copy = l.copy()
                                l_copy["symbol"] = sym
                                tracker_legs.append(l_copy)
                                entry_prices.append(pr)

                            self.tracker.add_legs(tracker_legs, entry_prices, side="SELL")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}", exc_info=True)

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    NiftyIronCondorStrategy().run()
