#!/usr/bin/env python3
"""
[CHANGELOG]
2025-04-14: Created Iron Condor Strategy for NIFTY.

best_nifty_options_strategy - NIFTY Options (OpenAlgo Web UI Compatible)
Iron Condor strategy for Nifty options, entering after 10 AM if straddle premium > 120.
"""
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from datetime import time as dt_time

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
sys.path.insert(0, strategies_dir)

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


class NiftyIronCondor:
    def __init__(self):
        self.logger = PrintLogger()
        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)

        # Configuration via environment variables
        self.strategy_name = os.getenv("STRATEGY_NAME", "NiftyIronCondor")
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
        self.sleep_seconds = int(os.getenv("SLEEP_SECONDS", "30"))
        self.expiry_refresh_sec = int(os.getenv("EXPIRY_REFRESH_SEC", "3600"))
        self.max_orders_per_day = int(os.getenv("MAX_ORDERS_PER_DAY", "1"))
        self.max_orders_per_hour = int(os.getenv("MAX_ORDERS_PER_HOUR", "1"))

        self.min_straddle_premium = float(os.getenv("MIN_STRADDLE_PREMIUM", "120"))

        # State tracking
        self.tracker = OptionPositionTracker(sl_pct=self.sl_pct, tp_pct=self.tp_pct, max_hold_min=self.max_hold_min)
        self.limiter = TradeLimiter(
            max_per_day=self.max_orders_per_day,
            max_per_hour=self.max_orders_per_hour,
            cooldown_seconds=self.cooldown_seconds
        )
        self.debouncer = SignalDebouncer()

        self.expiry = None
        self.last_expiry_refresh = 0
        self.entered_today = False

        self.all_open_legs = []  # Detailed tracking for exit: list of dicts

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_refresh) > self.expiry_refresh_sec:
            try:
                res = self.client.expiry(self.underlying, self.options_exchange, "options")
                if res and res.get("status") == "success" and res.get("data"):
                    expirations = res.get("data")
                    self.expiry = choose_nearest_expiry(expirations)
                    self.last_expiry_refresh = now
                    self.logger.info(f"Resolved nearest expiry: {self.expiry}")
                else:
                    self.logger.warning(f"Failed to fetch expiry: {res}")
            except Exception as e:
                self.logger.error(f"Error fetching expiry: {e}")

    def get_atm_and_straddle_premium(self, chain):
        atm_ce = None
        atm_pe = None

        for item in chain:
            ce = item.get("ce", {})
            pe = item.get("pe", {})
            if ce.get("label") == "ATM":
                atm_ce = float(ce.get("ltp", 0.0))
            if pe.get("label") == "ATM":
                atm_pe = float(pe.get("ltp", 0.0))

        if atm_ce is not None and atm_pe is not None:
            return atm_ce + atm_pe
        return 0.0

    def find_leg_by_offset(self, chain, offset, opt_type):
        for item in chain:
            opt = item.get(opt_type.lower(), {})
            if opt.get("label") == offset:
                return opt
        return None

    def _close_position(self, chain, exit_reason):
        self.logger.info(f"event=trade action=CLOSE reason={exit_reason}")
        if not self.all_open_legs:
            self.tracker.clear()
            return

        # Update current prices for open legs
        for leg in self.all_open_legs:
            for item in chain:
                if leg["option_type"] == "CE":
                    opt = item.get("ce", {})
                else:
                    opt = item.get("pe", {})
                if opt.get("symbol") == leg["symbol"]:
                    leg["current_price"] = float(opt.get("ltp", 0.0))
                    break

        # Sort legs to buy to cover first (closing short legs), then sell to close (closing long legs)
        sorted_legs = sorted(self.all_open_legs, key=lambda x: 0 if x["side"] == "SELL" else 1)

        for leg in sorted_legs:
            close_action = "BUY" if leg["side"] == "SELL" else "SELL"
            try:
                resp = self.api_client.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=leg["symbol"],
                    action=close_action,
                    exchange=self.options_exchange,
                    pricetype="MARKET",
                    product=self.product,
                    quantity=self.quantity,
                    position_size=0
                )
                self.logger.info(format_kv(symbol=leg["symbol"], action=close_action, ltp=leg.get("current_price", 0.0), msg="Close leg response", status=resp.get("status")))
            except Exception as e:
                self.logger.error(f"Error closing leg {leg['symbol']}: {e}")

        self.tracker.clear()
        self.all_open_legs = []

    def can_trade(self):
        ist = timezone(timedelta(hours=5, minutes=30))
        now = datetime.now(ist)

        # Don't enter before 10 AM
        if now.time() < dt_time(10, 0):
            return False

        # Don't enter after 2:30 PM (14:30)
        if now.time() > dt_time(14, 30):
            return False

        if self.entered_today:
            return False

        return self.limiter.allow()

    def run(self):
        self.logger.info(f"Starting {self.strategy_name} for {self.underlying}...")

        ist = timezone(timedelta(hours=5, minutes=30))
        last_day = datetime.now(ist).day

        while True:
            try:
                now_ist = datetime.now(ist)
                if now_ist.day != last_day:
                    self.entered_today = False
                    self.limiter.daily_trades = 0
                    last_day = now_ist.day

                # EOD square-off at 3:15 PM (15:15)
                if now_ist.time() >= dt_time(15, 15) and self.tracker.open_legs:
                    chain_resp = self.client.optionchain(
                        underlying=self.underlying,
                        exchange=self.underlying_exchange,
                        expiry_date=self.expiry,
                        strike_count=self.strike_count
                    )
                    chain = chain_resp.get("chain", []) if isinstance(chain_resp, dict) else []
                    self._close_position(chain, "eod_squareoff")
                    time.sleep(self.sleep_seconds)
                    continue

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
                    self.logger.warning(f"Invalid chain: {reason}")
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])

                # EXIT MANAGEMENT FIRST
                if self.tracker.open_legs:
                    exit_now, _legs, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # ENTRY LOGIC
                if not self.tracker.open_legs and self.can_trade():
                    straddle_premium = self.get_atm_and_straddle_premium(chain)

                    signal_condition = straddle_premium > self.min_straddle_premium

                    if self.debouncer.edge("iron_condor_entry", signal_condition):
                        self.logger.info(format_kv(spot=chain_resp.get("underlying_ltp", 0.0), straddle_premium=straddle_premium, signal="IRON_CONDOR_ENTRY"))

                        # Verify legs exist before placing order
                        ce_short_leg = self.find_leg_by_offset(chain, "OTM2", "CE")
                        pe_short_leg = self.find_leg_by_offset(chain, "OTM2", "PE")
                        ce_long_leg = self.find_leg_by_offset(chain, "OTM4", "CE")
                        pe_long_leg = self.find_leg_by_offset(chain, "OTM4", "PE")

                        if all([ce_short_leg, pe_short_leg, ce_long_leg, pe_long_leg]):
                            legs_config = [
                                {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                                {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": self.quantity, "product": self.product},
                                {"offset": "OTM2", "option_type": "CE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                                {"offset": "OTM2", "option_type": "PE", "action": "SELL", "quantity": self.quantity, "product": self.product},
                            ]

                            try:
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

                                    # Setup tracker state
                                    tracker_legs = [
                                        {"offset": "OTM4", "option_type": "CE"},
                                        {"offset": "OTM4", "option_type": "PE"},
                                        {"offset": "OTM2", "option_type": "CE"},
                                        {"offset": "OTM2", "option_type": "PE"},
                                    ]
                                    entry_prices = [
                                        float(ce_long_leg.get("ltp", 0.0)),
                                        float(pe_long_leg.get("ltp", 0.0)),
                                        float(ce_short_leg.get("ltp", 0.0)),
                                        float(pe_short_leg.get("ltp", 0.0)),
                                    ]
                                    self.tracker.add_legs(tracker_legs, entry_prices, side="SELL") # Overall position is net credit

                                    # Setup local precise leg tracking
                                    self.all_open_legs = [
                                        {"symbol": ce_long_leg.get("symbol"), "option_type": "CE", "side": "BUY", "entry_price": float(ce_long_leg.get("ltp", 0.0))},
                                        {"symbol": pe_long_leg.get("symbol"), "option_type": "PE", "side": "BUY", "entry_price": float(pe_long_leg.get("ltp", 0.0))},
                                        {"symbol": ce_short_leg.get("symbol"), "option_type": "CE", "side": "SELL", "entry_price": float(ce_short_leg.get("ltp", 0.0))},
                                        {"symbol": pe_short_leg.get("symbol"), "option_type": "PE", "side": "SELL", "entry_price": float(pe_short_leg.get("ltp", 0.0))},
                                    ]

                                    self.logger.info(f"event=trade action=ENTER reason=straddle_premium_{straddle_premium}")
                            except Exception as e:
                                self.logger.error(f"Error placing entry order: {e}")
                        else:
                            self.logger.warning("Could not find all required legs for Iron Condor.")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    NiftyIronCondor().run()
