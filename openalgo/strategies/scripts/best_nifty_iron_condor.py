#!/usr/bin/env python3
"""
Best Nifty Iron Condor - NIFTY Options (OpenAlgo Web UI Compatible)
Enters an Iron Condor after 10 AM if ATM straddle premium > 120, taking 40% SL and 50% TP on short legs.
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
    from trading_utils import APIClient, is_market_open
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
        self.strategy_name = os.getenv("STRATEGY_NAME", "best_nifty_iron_condor")
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
        self.min_straddle_premium = float(os.getenv("MIN_STRADDLE_PREMIUM", "120.0"))

        self.client = OptionChainClient(api_key=API_KEY, host=HOST)
        self.api_client = APIClient(api_key=API_KEY, host=HOST)
        self.tracker = OptionPositionTracker(sl_pct=self.sl_pct, tp_pct=self.tp_pct, max_hold_min=self.max_hold_min)
        self.limiter = TradeLimiter(max_per_day=self.max_orders_per_day, max_per_hour=self.max_orders_per_hour, cooldown_seconds=self.cooldown_seconds)
        self.debouncer = SignalDebouncer()

        self.expiry = os.getenv("EXPIRY_DATE")
        self.last_expiry_check = 0
        self.entered_today = False
        self.all_open_legs = []

    def ensure_expiry(self):
        now = time.time()
        if not self.expiry or (now - self.last_expiry_check > self.expiry_refresh_sec):
            try:
                res = self.client.expiry(self.underlying, self.options_exchange, "options")
                if res.get("status") == "success" and res.get("data"):
                    self.expiry = choose_nearest_expiry(res.get("data"))
                    self.last_expiry_check = now
                    self.logger.info(format_kv(event="expiry_updated", expiry=self.expiry))
            except Exception as e:
                self.logger.error(f"Error fetching expiry: {e}")

    def _get_atm_premium(self, chain):
        for item in chain:
            ce_label = item.get("ce", {}).get("label")
            pe_label = item.get("pe", {}).get("label")
            if ce_label == "ATM" or pe_label == "ATM":
                ce_ltp = safe_float(item.get("ce", {}).get("ltp"))
                pe_ltp = safe_float(item.get("pe", {}).get("ltp"))
                return ce_ltp + pe_ltp
        return 0.0

    def _get_option_symbol(self, chain, label, option_type):
        for item in chain:
            opt = item.get(option_type.lower(), {})
            if opt.get("label") == label:
                return opt.get("symbol")
        return None

    def _get_option_ltp(self, chain, label, option_type):
        for item in chain:
            opt = item.get(option_type.lower(), {})
            if opt.get("label") == label:
                return safe_float(opt.get("ltp"))
        return 0.0

    def can_trade(self):
        if self.entered_today:
            return False

        now = datetime.now()
        hour = now.hour
        minute = now.minute

        # Enter after 10:00 AM
        if hour < 10:
            return False

        # Do not enter after 3:00 PM
        if hour >= 15:
            return False

        return self.limiter.allow()

    def _close_position(self, chain, reason):
        self.logger.info(format_kv(event="closing_position", reason=reason))

        # Sort legs to prioritize BUY (to cover) over SELL (to close)
        sorted_legs = []
        buy_legs = [leg for leg in self.all_open_legs if leg["entry_action"] == "SELL"] # Short legs need BUY to cover
        sell_legs = [leg for leg in self.all_open_legs if leg["entry_action"] == "BUY"] # Long legs need SELL to close
        sorted_legs.extend(buy_legs)
        sorted_legs.extend(sell_legs)

        for leg in sorted_legs:
            action = "BUY" if leg["entry_action"] == "SELL" else "SELL"
            try:
                resp = self.api_client.placesmartorder(
                    strategy=self.strategy_name,
                    symbol=leg["symbol"],
                    action=action,
                    exchange=self.options_exchange,
                    pricetype="MARKET",
                    product=self.product,
                    quantity=self.quantity,
                    position_size=0 # Close position
                )
                self.logger.info(format_kv(event="trade", action=f"close_{action}", symbol=leg["symbol"], response=resp))
            except Exception as e:
                self.logger.error(f"Error closing leg {leg['symbol']}: {e}")

        self.tracker.clear()
        self.all_open_legs = []

    def run(self):
        self.logger.info(f"Starting NiftyIronCondorStrategy for {self.underlying}")
        while True:
            try:
                if not is_market_open():
                    time.sleep(self.sleep_seconds)
                    continue

                self.ensure_expiry()
                if not self.expiry:
                    time.sleep(self.sleep_seconds)
                    continue

                now = datetime.now()
                # EOD Square-off at 3:15 PM
                if now.hour == 15 and now.minute >= 15:
                    if self.all_open_legs:
                        # Dummy chain for closing
                        self._close_position([], "eod_square_off")
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
                    time.sleep(self.sleep_seconds)
                    continue

                chain = chain_resp.get("chain", [])
                spot = chain_resp.get("underlying_ltp", 0.0)

                # EXIT MANAGEMENT FIRST
                if self.tracker.open_legs:
                    exit_now, _, exit_reason = self.tracker.should_exit(chain)
                    if exit_now:
                        self._close_position(chain, exit_reason)
                        time.sleep(self.sleep_seconds)
                        continue

                # CALCULATE INDICATORS
                straddle_premium = self._get_atm_premium(chain)

                self.logger.info(format_kv(spot=spot, straddle_premium=straddle_premium, open_legs=len(self.all_open_legs)))

                # ENTRY LOGIC
                signal = straddle_premium > self.min_straddle_premium
                trigger = self.debouncer.edge("iron_condor_entry", signal)

                if not self.all_open_legs and self.can_trade() and trigger:
                    self.logger.info(format_kv(event="entry_signal", reason="premium_high", premium=straddle_premium))

                    # Ensure symbols exist
                    otm4_ce = self._get_option_symbol(chain, "OTM4", "CE")
                    otm4_pe = self._get_option_symbol(chain, "OTM4", "PE")
                    otm2_ce = self._get_option_symbol(chain, "OTM2", "CE")
                    otm2_pe = self._get_option_symbol(chain, "OTM2", "PE")

                    if not all([otm4_ce, otm4_pe, otm2_ce, otm2_pe]):
                        self.logger.warning("Could not find all required symbols for Iron Condor")
                        time.sleep(self.sleep_seconds)
                        continue

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
                            exchange=self.underlying_exchange,
                            expiry_date=self.expiry,
                            legs=legs
                        )
                        self.logger.info(format_kv(event="trade", action="open_iron_condor", response=resp))

                        if resp.get("status") == "success":
                            self.limiter.record()
                            self.entered_today = True

                            # Track only short legs for SL/TP in OptionPositionTracker
                            short_legs = [leg for leg in legs if leg["action"] == "SELL"]
                            entry_prices = [
                                self._get_option_ltp(chain, "OTM2", "CE"),
                                self._get_option_ltp(chain, "OTM2", "PE")
                            ]
                            self.tracker.add_legs(short_legs, entry_prices, side="SELL")

                            # Track all legs in strategy state for closing
                            self.all_open_legs = [
                                {"symbol": otm4_ce, "entry_action": "BUY", "offset": "OTM4", "type": "CE"},
                                {"symbol": otm4_pe, "entry_action": "BUY", "offset": "OTM4", "type": "PE"},
                                {"symbol": otm2_ce, "entry_action": "SELL", "offset": "OTM2", "type": "CE"},
                                {"symbol": otm2_pe, "entry_action": "SELL", "offset": "OTM2", "type": "PE"},
                            ]
                    except Exception as e:
                        self.logger.error(f"Error opening Iron Condor: {e}")

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")

            time.sleep(self.sleep_seconds)

if __name__ == "__main__":
    NiftyIronCondorStrategy().run()
